"""Thread-safe in-memory alert store (v1). Seeded with demo alerts for local UI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import RLock

from action.api.app.models import AlertRecord, ComponentBreakdown, MetricsSummary


class AlertStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._alerts: dict[str, AlertRecord] = {}

    def upsert(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            existing = self._alerts.get(alert.alert_id)
            if existing and existing.acknowledged:
                alert.acknowledged = True
                alert.acknowledged_at = existing.acknowledged_at
                alert.acknowledge_note = existing.acknowledge_note
            self._alerts[alert.alert_id] = alert
            return alert

    def list(
        self,
        *,
        include_acknowledged: bool = True,
        patient_id: str | None = None,
        limit: int = 100,
    ) -> list[AlertRecord]:
        with self._lock:
            items = list(self._alerts.values())
        if patient_id:
            items = [a for a in items if a.patient_id == patient_id]
        if not include_acknowledged:
            items = [a for a in items if not a.acknowledged]
        items.sort(key=lambda a: a.event_time, reverse=True)
        return items[:limit]

    def get(self, alert_id: str) -> AlertRecord | None:
        with self._lock:
            return self._alerts.get(alert_id)

    def acknowledge(self, alert_id: str, note: str | None = None) -> AlertRecord | None:
        with self._lock:
            alert = self._alerts.get(alert_id)
            if alert is None:
                return None
            updated = alert.model_copy(
                update={
                    "acknowledged": True,
                    "acknowledged_at": datetime.now(UTC),
                    "acknowledge_note": note,
                }
            )
            self._alerts[alert_id] = updated
            return updated

    def metrics(self) -> MetricsSummary:
        items = self.list(limit=10_000)
        by_tier: dict[str, int] = {}
        ack = 0
        for a in items:
            by_tier[a.tier] = by_tier.get(a.tier, 0) + 1
            if a.acknowledged:
                ack += 1
        return MetricsSummary(
            total_alerts=len(items),
            open_alerts=len(items) - ack,
            acknowledged_alerts=ack,
            by_tier=by_tier,
        )

    def clear(self) -> None:
        with self._lock:
            self._alerts.clear()


def seed_demo_alerts(store: AlertStore) -> None:
    """Deterministic demo cohort for local dashboard / API smoke tests."""
    now = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    demos = [
        AlertRecord(
            alert_id="alert-demo-critical-001",
            patient_id="Patient/synthea-icu-001",
            encounter_id="Encounter/enc-001",
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
        ),
        AlertRecord(
            alert_id="alert-demo-urgent-002",
            patient_id="Patient/synthea-icu-002",
            encounter_id="Encounter/enc-002",
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
        ),
        AlertRecord(
            alert_id="alert-demo-watch-003",
            patient_id="Patient/synthea-ward-003",
            encounter_id="Encounter/enc-003",
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
            acknowledged=True,
            acknowledged_at=now - timedelta(hours=2),
            acknowledge_note="Reviewed — trending down",
        ),
    ]
    for alert in demos:
        store.upsert(alert)


STORE = AlertStore()
seed_demo_alerts(STORE)
