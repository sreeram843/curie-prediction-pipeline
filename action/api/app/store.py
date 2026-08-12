"""Alert store backends (CURIE-017).

Default is SQLite-durable when ``CURIE_ALERT_DB`` is set (or ``data/curie_alerts.sqlite``
when ``CURIE_ALERT_STORE=sqlite``). Tests and local smoke may use ``memory``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any

from action.api.app.models import AlertRecord, ComponentBreakdown, MetricsSummary
from eval.episodes.arbiter import EpisodeArbiter, EpisodeConfig


class MemoryAlertStore:
    """In-memory store retained for unit tests and ephemeral demos."""

    def __init__(self, *, arbiter: EpisodeArbiter | None = None) -> None:
        self._lock = RLock()
        self._alerts: dict[str, AlertRecord] = {}
        self.arbiter = arbiter or EpisodeArbiter(EpisodeConfig())

    def upsert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            existing = self._alerts.get(alert.alert_id)
            if existing and existing.acknowledged:
                alert.acknowledged = True
                alert.acknowledged_at = existing.acknowledged_at
                alert.acknowledge_note = existing.acknowledge_note
                alert.resolution_state = "acknowledged"
            self._alerts[alert.alert_id] = alert
            self.arbiter.ingest(alert)
            return alert

    def ingest_kafka(
        self, alert: AlertRecord, *, idempotency_key: str
    ) -> tuple[AlertRecord, bool]:
        # Memory path: alert_id upsert is the only idempotency key.
        with self._lock:
            existed = alert.alert_id in self._alerts
        return self.upsert(alert), not existed

    def list(
        self,
        *,
        include_acknowledged: bool = True,
        patient_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AlertRecord]:
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        with self._lock:
            items = list(self._alerts.values())
        if patient_id:
            items = [a for a in items if a.patient_id == patient_id]
        if not include_acknowledged:
            items = [a for a in items if not a.acknowledged]
        items.sort(key=lambda a: a.event_time, reverse=True)
        return items[offset : offset + limit]

    def count(
        self,
        *,
        include_acknowledged: bool = True,
        patient_id: str | None = None,
    ) -> int:
        with self._lock:
            items = list(self._alerts.values())
        if patient_id:
            items = [a for a in items if a.patient_id == patient_id]
        if not include_acknowledged:
            items = [a for a in items if not a.acknowledged]
        return len(items)

    def get(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def acknowledge(self, alert_id: str, note: str | None = None) -> AlertRecord | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            data = alert.model_dump()
            data.update(
                {
                    "acknowledged": True,
                    "acknowledged_at": datetime.now(UTC),
                    "acknowledge_note": note,
                    "resolution_state": "acknowledged",
                    "signal": None,
                }
            )
            updated = AlertRecord.model_validate(data)
            self._alerts[alert_id] = updated
            return updated

    def metrics(self) -> MetricsSummary:
        # Full scan — no silent 10k truncation (CURIE-017).
        with self._lock:
            items = list(self._alerts.values())
        by_tier: dict[str, int] = {}
        by_routing: dict[str, int] = {}
        by_indicator: dict[str, int] = {}
        ack = 0
        for a in items:
            by_tier[a.tier] = by_tier.get(a.tier, 0) + 1
            route = a.routing or "unset"
            by_routing[route] = by_routing.get(route, 0) + 1
            by_indicator[a.indicator] = by_indicator.get(a.indicator, 0) + 1
            if a.acknowledged:
                ack += 1
        return MetricsSummary(
            total_alerts=len(items),
            open_alerts=len(items) - ack,
            acknowledged_alerts=ack,
            by_tier=by_tier,
            by_routing=by_routing,
            by_indicator=by_indicator,
        )

    def attach_narrative(
        self,
        alert_id: str,
        *,
        status: str,
        narrative: str | None,
        claims: list[dict],
        quarantine_reason: str | None,
        model_name: str | None,
    ) -> AlertRecord | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            updated = alert.model_copy(
                update={
                    "narrative_status": status,
                    "narrative_claims": claims,
                    "narrative": narrative,
                    "quarantine_reason": quarantine_reason,
                    "grp_model_name": model_name,
                }
            )
            self._alerts[alert_id] = updated
            return updated

    def clear(self) -> None:
        with self._lock:
            self._alerts.clear()
            self.arbiter = EpisodeArbiter(EpisodeConfig())

    def list_episodes(self, *, patient_id: str | None = None, limit: int = 100):
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            items = self.arbiter.list_all()
        if patient_id:
            items = [e for e in items if e.patient_id == patient_id]
        return items[:limit]

    def get_episode(self, episode_id: str):
        return self.arbiter.get(episode_id)


# Backward-compatible name
AlertStore = MemoryAlertStore


def open_store() -> Any:
    """Construct the process-wide store from environment.

    - If ``CURIE_ALERT_DB`` is set → SQLite durable store at that path.
    - Else if ``CURIE_ALERT_STORE=sqlite`` → ``data/curie_alerts.sqlite``.
    - Else → in-memory (tests / ephemeral demos).
    """
    backend = os.getenv("CURIE_ALERT_STORE", "").strip().lower()
    db_path = os.getenv("CURIE_ALERT_DB", "").strip()
    use_sqlite = bool(db_path) or backend in {"sqlite", "durable", "db"}
    if not use_sqlite:
        return MemoryAlertStore()

    from action.api.app.durable_store import DurableAlertStore

    path = db_path or "data/curie_alerts.sqlite"
    retention_raw = os.getenv("CURIE_ALERT_RETENTION_DAYS", "").strip()
    retention = int(retention_raw) if retention_raw.isdigit() else None
    return DurableAlertStore(path, retention_days=retention)


def seed_demo_alerts(store: Any) -> None:
    """Deterministic demo cohort for local dashboard / API smoke tests."""
    now = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    demos = [
        AlertRecord(
            alert_id="alert-demo-critical-001",
            patient_id="Patient/p-48102",
            patient_name="Maya Ellison",
            encounter_id="Encounter/enc-001",
            indicator="sofa-deterioration",
            event_time=now - timedelta(minutes=12),
            ingest_time=now - timedelta(minutes=11),
            score=8,
            completeness="partial",
            tier="critical",
            component_breakdown=[
                ComponentBreakdown(
                    name="coagulation",
                    points=3,
                    evidence_ids=["Observation/plt-88"],
                ),
                ComponentBreakdown(
                    name="liver",
                    points=2,
                    evidence_ids=["Observation/bili-12"],
                ),
                ComponentBreakdown(
                    name="renal",
                    points=2,
                    evidence_ids=["Observation/cr-44"],
                ),
                ComponentBreakdown(name="respiration", missing=True),
                ComponentBreakdown(
                    name="cardiovascular",
                    points=1,
                    evidence_ids=["Observation/map-9"],
                ),
                ComponentBreakdown(name="cns", missing=True),
            ],
            missing_components=["respiration", "cns"],
            evidence_ids=[
                "Observation/plt-88",
                "Observation/bili-12",
                "Observation/cr-44",
                "Observation/map-9",
            ],
            governance_path="governed",
            routing="interruptive",
            positive_components=4,
        ),
        AlertRecord(
            alert_id="alert-demo-urgent-002",
            patient_id="Patient/p-55217",
            patient_name="James Okonkwo",
            encounter_id="Encounter/enc-002",
            indicator="sofa-deterioration",
            event_time=now - timedelta(hours=1),
            ingest_time=now - timedelta(hours=1) + timedelta(seconds=40),
            score=5,
            completeness="complete",
            tier="urgent",
            component_breakdown=[
                ComponentBreakdown(
                    name="coagulation",
                    points=2,
                    evidence_ids=["Observation/plt-21"],
                ),
                ComponentBreakdown(
                    name="renal",
                    points=2,
                    evidence_ids=["Observation/cr-21"],
                ),
                ComponentBreakdown(
                    name="cns",
                    points=1,
                    evidence_ids=["Observation/gcs-21"],
                ),
            ],
            evidence_ids=["Observation/plt-21", "Observation/cr-21", "Observation/gcs-21"],
            governance_path="governed",
            routing="interruptive",
            positive_components=3,
        ),
        AlertRecord(
            alert_id="alert-demo-watch-003",
            patient_id="Patient/p-60344",
            patient_name="Priya Natarajan",
            encounter_id="Encounter/enc-003",
            indicator="sofa-deterioration",
            event_time=now - timedelta(hours=3),
            ingest_time=now - timedelta(hours=3),
            score=2,
            completeness="complete",
            tier="watch",
            component_breakdown=[
                ComponentBreakdown(
                    name="renal",
                    points=1,
                    evidence_ids=["Observation/cr-3"],
                ),
                ComponentBreakdown(
                    name="liver",
                    points=1,
                    evidence_ids=["Observation/bili-3"],
                ),
            ],
            evidence_ids=["Observation/cr-3", "Observation/bili-3"],
            governance_path="governed",
            routing="passive",
            positive_components=2,
            acknowledged=True,
            acknowledged_at=now - timedelta(hours=2),
            acknowledge_note="Reviewed — trending down",
        ),
        AlertRecord(
            alert_id="alert-demo-aki-urgent-004",
            patient_id="Patient/p-71908",
            patient_name="Daniel Romero",
            encounter_id="Encounter/enc-004",
            indicator="aki",
            event_time=now - timedelta(minutes=40),
            ingest_time=now - timedelta(minutes=39),
            score=4,
            completeness="complete",
            tier="urgent",
            component_breakdown=[
                ComponentBreakdown(
                    name="creatinine",
                    points=4,
                    evidence_ids=["Observation/cr-aki-now"],
                ),
                ComponentBreakdown(
                    name="baseline_creatinine",
                    points=0,
                    evidence_ids=["Observation/cr-aki-base"],
                ),
            ],
            evidence_ids=["Observation/cr-aki-now", "Observation/cr-aki-base"],
            rule_bundle_id="aki-kdigo",
            rule_version="0.4.0",
            governance_path="governed",
            routing="passive",
            page_deferred_reason="page_persistence",
            positive_components=1,
        ),
        AlertRecord(
            alert_id="alert-demo-episode-sofa-005",
            patient_id="Patient/p-ep-901",
            patient_name="Elena Vargas",
            encounter_id="Encounter/enc-ep-1",
            indicator="sofa-deterioration",
            event_time=now - timedelta(minutes=25),
            ingest_time=now - timedelta(minutes=24),
            score=7,
            completeness="partial",
            tier="critical",
            component_breakdown=[
                ComponentBreakdown(
                    name="cardiovascular",
                    points=3,
                    evidence_ids=["Observation/map-ep"],
                ),
                ComponentBreakdown(
                    name="renal",
                    points=2,
                    evidence_ids=["Observation/cr-ep"],
                ),
            ],
            evidence_ids=["Observation/map-ep", "Observation/cr-ep"],
            governance_path="governed",
            routing="interruptive",
            positive_components=2,
        ),
        AlertRecord(
            alert_id="alert-demo-episode-aki-006",
            patient_id="Patient/p-ep-901",
            patient_name="Elena Vargas",
            encounter_id="Encounter/enc-ep-1",
            indicator="aki",
            event_time=now - timedelta(minutes=20),
            ingest_time=now - timedelta(minutes=19),
            score=4,
            completeness="complete",
            tier="urgent",
            component_breakdown=[
                ComponentBreakdown(
                    name="creatinine",
                    points=4,
                    evidence_ids=["Observation/cr-ep-aki"],
                ),
            ],
            evidence_ids=["Observation/cr-ep-aki"],
            rule_bundle_id="aki-kdigo",
            rule_version="0.4.0",
            governance_path="governed",
            routing="interruptive",
            positive_components=1,
        ),
        AlertRecord(
            alert_id="alert-demo-episode-hypo-007",
            patient_id="Patient/p-ep-901",
            patient_name="Elena Vargas",
            encounter_id="Encounter/enc-ep-1",
            indicator="hypotension",
            signal_kind="risk",
            event_time=now - timedelta(minutes=18),
            ingest_time=now - timedelta(minutes=17),
            score=3,
            completeness="complete",
            tier="urgent",
            component_breakdown=[
                ComponentBreakdown(
                    name="map",
                    points=3,
                    evidence_ids=["Observation/map-low"],
                ),
            ],
            evidence_ids=["Observation/map-low"],
            rule_bundle_id="hypotension-demo",
            rule_version="0.1.0",
            governance_path="governed",
            routing="interruptive",
            positive_components=1,
        ),
        AlertRecord(
            alert_id="alert-demo-resp-urgent-008",
            patient_id="Patient/p-88201",
            patient_name="Noah Chen",
            encounter_id="Encounter/enc-008",
            indicator="respiratory-deterioration",
            signal_kind="risk",
            event_time=now - timedelta(minutes=8),
            ingest_time=now - timedelta(minutes=7),
            score=4,
            stage=2,
            completeness="complete",
            tier="urgent",
            component_breakdown=[
                ComponentBreakdown(
                    name="oxygenation",
                    points=4,
                    evidence_ids=["Observation/spo2-resp"],
                ),
                ComponentBreakdown(
                    name="respiratory_rate",
                    points=4,
                    evidence_ids=["Observation/rr-resp"],
                ),
                ComponentBreakdown(
                    name="oxygen_support",
                    points=4,
                    evidence_ids=["Observation/hfnc"],
                ),
            ],
            evidence_ids=[
                "Observation/spo2-resp",
                "Observation/rr-resp",
                "Observation/hfnc",
            ],
            criteria_met=["ratio_lt_300:spo2_fio2", "rr_ge_30", "oxygen_device:high_flow"],
            required_inputs=[
                "oxygenation",
                "respiratory_rate",
                "oxygen_support",
                "blood_gas",
            ],
            rule_bundle_id="resp-deterioration",
            rule_version="0.1.0",
            governance_path="governed",
            routing="interruptive",
            positive_components=3,
        ),
        AlertRecord(
            alert_id="alert-demo-resp-ep-sofa-009",
            patient_id="Patient/p-ep-902",
            patient_name="Aisha Rahman",
            encounter_id="Encounter/enc-ep-2",
            indicator="sofa-deterioration",
            event_time=now - timedelta(minutes=15),
            ingest_time=now - timedelta(minutes=14),
            score=5,
            completeness="partial",
            tier="urgent",
            component_breakdown=[
                ComponentBreakdown(
                    name="respiration",
                    points=3,
                    evidence_ids=["Observation/pf-ep2"],
                ),
                ComponentBreakdown(
                    name="cardiovascular",
                    points=2,
                    evidence_ids=["Observation/map-ep2"],
                ),
            ],
            evidence_ids=["Observation/pf-ep2", "Observation/map-ep2"],
            governance_path="governed",
            routing="interruptive",
            positive_components=2,
        ),
        AlertRecord(
            alert_id="alert-demo-resp-ep-010",
            patient_id="Patient/p-ep-902",
            patient_name="Aisha Rahman",
            encounter_id="Encounter/enc-ep-2",
            indicator="respiratory-deterioration",
            signal_kind="risk",
            event_time=now - timedelta(minutes=12),
            ingest_time=now - timedelta(minutes=11),
            score=6,
            stage=3,
            completeness="complete",
            tier="critical",
            component_breakdown=[
                ComponentBreakdown(
                    name="oxygenation",
                    points=6,
                    evidence_ids=["Observation/pf-ep2"],
                ),
                ComponentBreakdown(
                    name="oxygen_support",
                    points=6,
                    evidence_ids=["Observation/vent-ep2"],
                ),
            ],
            evidence_ids=["Observation/pf-ep2", "Observation/vent-ep2"],
            criteria_met=["ratio_lt_100:pao2_fio2", "mechanically_ventilated"],
            rule_bundle_id="resp-deterioration",
            rule_version="0.1.0",
            governance_path="governed",
            routing="interruptive",
            positive_components=2,
        ),
    ]
    for alert in demos:
        store.upsert(alert)


def _bootstrap_store() -> Any:
    store = open_store()
    seed = os.getenv("CURIE_SEED_DEMO", "true").lower() in {"1", "true", "yes"}
    if seed and store.count() == 0:
        seed_demo_alerts(store)
    return store


STORE = _bootstrap_store()
