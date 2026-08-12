"""Investor demonstration scenarios (CURIE-021).

Replays a multi-signal patient timeline, compares naive/passive/interruptive
volume, surfaces evidence + rule hashes, and verifies duplicate / out-of-order /
restart survival — without touching production scoring knobs.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from action.api.app.durable_store import DurableAlertStore
from action.api.app.models import AlertRecord, ComponentBreakdown
from action.api.app.store import MemoryAlertStore
from eval.episodes.arbiter import EpisodeArbiter, EpisodeConfig

DEMO_PATIENT = "Patient/p-investor-001"
DEMO_NAME = "Elena Vargas (investor demo)"
DEMO_ENCOUNTER = "Encounter/enc-investor-1"
FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
REPORT_PATH = FROZEN_DIR / "demo_report.v1.json"


def _rule_hash(bundle_id: str, version: str) -> str:
    raw = f"{bundle_id}@{version}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _base_time() -> datetime:
    return datetime(2024, 6, 15, 14, 0, tzinfo=UTC)


def timeline_alerts() -> list[AlertRecord]:
    """Ordered clinical timeline: SOFA → AKI → hypotension → respiratory update."""
    t0 = _base_time()
    steps = [
        {
            "alert_id": "inv-sofa-1",
            "minutes": 0,
            "indicator": "sofa-deterioration",
            "score": 6,
            "tier": "urgent",
            "routing": "interruptive",
            "bundle": ("sepsis-sofa", "0.2.0"),
            "evidence": ["Observation/map-inv-1", "Observation/cr-inv-1"],
            "components": [
                ComponentBreakdown(
                    name="cardiovascular", points=3, evidence_ids=["Observation/map-inv-1"]
                ),
                ComponentBreakdown(
                    name="renal", points=2, evidence_ids=["Observation/cr-inv-1"]
                ),
            ],
        },
        {
            "alert_id": "inv-aki-1",
            "minutes": 25,
            "indicator": "aki",
            "score": 3,
            "tier": "urgent",
            "routing": "interruptive",
            "bundle": ("aki-kdigo", "0.4.0"),
            "evidence": ["Observation/cr-inv-aki"],
            "components": [
                ComponentBreakdown(
                    name="creatinine", points=3, evidence_ids=["Observation/cr-inv-aki"]
                ),
            ],
        },
        {
            "alert_id": "inv-hypo-1",
            "minutes": 40,
            "indicator": "hypotension",
            "score": 3,
            "tier": "urgent",
            "routing": "interruptive",
            "bundle": ("hypotension-demo", "0.1.0"),
            "evidence": ["Observation/map-inv-low"],
            "components": [
                ComponentBreakdown(
                    name="map", points=3, evidence_ids=["Observation/map-inv-low"]
                ),
            ],
        },
        {
            "alert_id": "inv-sofa-2",
            "minutes": 55,
            "indicator": "sofa-deterioration",
            "score": 8,
            "tier": "critical",
            "routing": "interruptive",
            "bundle": ("sepsis-sofa", "0.2.0"),
            "evidence": [
                "Observation/map-inv-2",
                "Observation/cr-inv-2",
                "Observation/plt-inv-2",
            ],
            "components": [
                ComponentBreakdown(
                    name="cardiovascular", points=4, evidence_ids=["Observation/map-inv-2"]
                ),
                ComponentBreakdown(
                    name="renal", points=2, evidence_ids=["Observation/cr-inv-2"]
                ),
                ComponentBreakdown(
                    name="coagulation", points=2, evidence_ids=["Observation/plt-inv-2"]
                ),
            ],
        },
        {
            "alert_id": "inv-watch-1",
            "minutes": 90,
            "indicator": "sofa-deterioration",
            "score": 2,
            "tier": "watch",
            "routing": "passive",
            "bundle": ("sepsis-sofa", "0.2.0"),
            "evidence": ["Observation/cr-inv-watch"],
            "components": [
                ComponentBreakdown(
                    name="renal", points=1, evidence_ids=["Observation/cr-inv-watch"]
                ),
            ],
        },
    ]
    out: list[AlertRecord] = []
    for step in steps:
        bid, ver = step["bundle"]
        et = t0 + timedelta(minutes=int(step["minutes"]))
        out.append(
            AlertRecord(
                alert_id=str(step["alert_id"]),
                patient_id=DEMO_PATIENT,
                patient_name=DEMO_NAME,
                encounter_id=DEMO_ENCOUNTER,
                indicator=str(step["indicator"]),
                event_time=et,
                ingest_time=et + timedelta(seconds=30),
                score=int(step["score"]),
                completeness="complete",
                tier=str(step["tier"]),
                component_breakdown=list(step["components"]),
                evidence_ids=list(step["evidence"]),
                rule_bundle_id=bid,
                rule_version=ver,
                rule_bundle_hash=_rule_hash(bid, ver),
                governance_path="governed",
                routing=step["routing"],  # type: ignore[arg-type]
                positive_components=len(step["components"]),
            )
        )
    return out


def volume_comparison(alerts: list[AlertRecord]) -> dict[str, Any]:
    """Naive = every score alert; governed splits passive vs interruptive."""
    naive = len(alerts)
    passive = sum(1 for a in alerts if a.routing == "passive")
    interruptive = sum(1 for a in alerts if a.routing == "interruptive")
    # Episode arbitration: one dominant interruptive page family vs per-signal pages
    arb = EpisodeArbiter(EpisodeConfig())
    pages = 0
    for alert in alerts:
        result = arb.ingest(alert)
        if result.should_page:
            pages += 1
    return {
        "naive_alert_count": naive,
        "governed_passive_count": passive,
        "governed_interruptive_signal_count": interruptive,
        "episode_interruptive_pages": pages,
        "reduction_vs_naive_pages": round(pages / naive, 3) if naive else None,
        "note": (
            "Naive counts every signal emission as a page. "
            "Episode arbitration collapses correlated interruptive signals."
        ),
    }


def replay_timeline(store: MemoryAlertStore | DurableAlertStore) -> dict[str, Any]:
    alerts = timeline_alerts()
    steps: list[dict[str, Any]] = []
    for alert in alerts:
        store.upsert(alert)
        episodes = store.list_episodes(patient_id=DEMO_PATIENT)
        ep = episodes[0] if episodes else None
        steps.append(
            {
                "alert_id": alert.alert_id,
                "event_time": alert.event_time.isoformat(),
                "indicator": alert.indicator,
                "tier": alert.tier,
                "routing": alert.routing,
                "score": alert.score,
                "evidence_ids": list(alert.evidence_ids),
                "rule_bundle_id": alert.rule_bundle_id,
                "rule_version": alert.rule_version,
                "rule_bundle_hash": alert.rule_bundle_hash,
                "episode_id": ep.episode_id if ep else None,
                "episode_signals": len(ep.signals) if ep else 0,
                "dominant": ep.dominant_signal_type if ep else None,
            }
        )
    episodes = store.list_episodes(patient_id=DEMO_PATIENT)
    assert episodes, "expected one investor-demo episode"
    primary = episodes[0]
    return {
        "patient_id": DEMO_PATIENT,
        "steps": steps,
        "final_episode": primary.to_public_dict(),
        "volume": volume_comparison(alerts),
        "signals_merged": len(primary.signals),
        "single_episode": len(episodes) == 1,
    }


def chaos_duplicate(store: MemoryAlertStore) -> dict[str, Any]:
    alert = timeline_alerts()[0]
    store.upsert(alert)
    store.upsert(deepcopy(alert))
    store.upsert(deepcopy(alert))
    listed = store.list(patient_id=DEMO_PATIENT)
    matching = [a for a in listed if a.alert_id == alert.alert_id]
    return {
        "scenario": "duplicate_upsert",
        "passed": len(matching) == 1,
        "alert_copies": len(matching),
    }


def chaos_out_of_order(store: MemoryAlertStore) -> dict[str, Any]:
    alerts = timeline_alerts()
    # Deliver later events first, then earlier ones
    for alert in reversed(alerts):
        store.upsert(alert)
    episodes = store.list_episodes(patient_id=DEMO_PATIENT)
    ids = {a.alert_id for a in store.list(patient_id=DEMO_PATIENT)}
    return {
        "scenario": "out_of_order_ingest",
        "passed": len(ids) == len(alerts) and len(episodes) == 1,
        "alert_count": len(ids),
        "episode_count": len(episodes),
        "dominant": episodes[0].dominant_signal_type if episodes else None,
    }


def chaos_restart(tmp_db: Path) -> dict[str, Any]:
    alerts = timeline_alerts()
    s1 = DurableAlertStore(tmp_db)
    for alert in alerts:
        s1.ingest_kafka(alert, idempotency_key=f"kafka:{alert.alert_id}")
    # Duplicate kafka delivery after "crash"
    dup = alerts[1]
    _, created_during = s1.ingest_kafka(dup, idempotency_key=f"kafka:{dup.alert_id}")
    before_ids = {a.alert_id for a in s1.list(patient_id=DEMO_PATIENT)}
    before_eps = s1.list_episodes(patient_id=DEMO_PATIENT)
    before_ep_count = len(before_eps)
    before_ep_ids = {e.episode_id for e in before_eps}
    before_signals = len(before_eps[0].signals) if before_ep_count else 0
    s1.close()
    # New process
    s2 = DurableAlertStore(tmp_db)
    after_ids = {a.alert_id for a in s2.list(patient_id=DEMO_PATIENT)}
    after_eps = s2.list_episodes(patient_id=DEMO_PATIENT)
    after_ep_count = len(after_eps)
    after_ep_ids = {e.episode_id for e in after_eps}
    after_signals = len(after_eps[0].signals) if after_eps else 0
    # Duplicate again post-restart
    again, created = s2.ingest_kafka(dup, idempotency_key=f"kafka:{dup.alert_id}")
    s2.close()
    return {
        "scenario": "restart_plus_duplicate_kafka",
        "passed": (
            before_ids == after_ids
            and before_ep_ids == after_ep_ids
            and before_ep_count == after_ep_count == 1
            and before_signals == after_signals
            and len(after_ids) == len(alerts)
            and created_during is False
            and created is False
            and again.alert_id == dup.alert_id
        ),
        "alert_count": len(after_ids),
        "episode_count": after_ep_count,
        "episode_ids_stable": before_ep_ids == after_ep_ids,
        "signals_in_episode": after_signals,
        "duplicate_created": created,
    }


def run_demo(
    *,
    db_path: Path | None = None,
    write: bool = True,
    report_path: Path | None = None,
) -> dict[str, Any]:
    store = MemoryAlertStore()
    timeline = replay_timeline(store)
    chaos_store_a = MemoryAlertStore()
    chaos_store_b = MemoryAlertStore()
    tmp = db_path or (FROZEN_DIR / "_investor_demo_tmp.sqlite")
    if tmp.exists():
        tmp.unlink()
    try:
        chaos = {
            "duplicate": chaos_duplicate(chaos_store_a),
            "out_of_order": chaos_out_of_order(chaos_store_b),
            "restart": chaos_restart(tmp),
        }
    finally:
        if tmp.exists() and db_path is None:
            tmp.unlink()

    evidence_surface = [
        {
            "alert_id": step["alert_id"],
            "evidence_ids": step["evidence_ids"],
            "rule_bundle_id": step["rule_bundle_id"],
            "rule_version": step["rule_version"],
            "rule_bundle_hash": step["rule_bundle_hash"],
        }
        for step in timeline["steps"]
    ]

    report = {
        "schema_version": "1.0.0",
        "curie_ticket": "CURIE-021",
        "disclaimer": "Synthetic investor demo — not clinical validation.",
        "timeline": timeline,
        "evidence_and_hashes": evidence_surface,
        "chaos": chaos,
        "chaos_all_passed": all(c["passed"] for c in chaos.values()),
        "claims_matrix_path": "eval/investor_demo/frozen/claims_matrix.v1.json",
    }
    if write:
        out = report_path or REPORT_PATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return report
