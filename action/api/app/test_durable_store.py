"""CURIE-017: durable alert store (restart, dedupe, metrics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from action.api.app.db import SCHEMA_VERSION, connect, migrate
from action.api.app.durable_store import DurableAlertStore
from action.api.app.models import AlertRecord
from action.api.app.store import MemoryAlertStore, seed_demo_alerts


def _alert(aid: str, *, minutes: int = 0, ack: bool = False) -> AlertRecord:
    now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
    return AlertRecord(
        alert_id=aid,
        patient_id="Patient/p-1",
        encounter_id="Encounter/e-1",
        indicator="sofa-deterioration",
        event_time=now - timedelta(minutes=minutes),
        score=4,
        tier="urgent",
        completeness="complete",
        routing="interruptive",
        acknowledged=ack,
        acknowledged_at=now if ack else None,
        resolution_state="acknowledged" if ack else "open",
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
    )


def test_migrate_creates_schema(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    conn = connect(path)
    assert migrate(conn) == SCHEMA_VERSION
    assert migrate(conn) == SCHEMA_VERSION  # idempotent
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "alerts" in tables
    assert "episodes" in tables
    assert "kafka_dedupe" in tables
    assert "rule_versions" in tables
    assert "audit_log" in tables
    conn.close()


def test_restart_preserves_alerts_and_acknowledgements(tmp_path: Path) -> None:
    path = tmp_path / "restart.db"
    s1 = DurableAlertStore(path)
    seed_demo_alerts(s1)
    before = s1.count()
    target = s1.get("alert-demo-critical-001")
    assert target is not None
    s1.acknowledge(target.alert_id, note="kept across restart")
    s1.close()

    s2 = DurableAlertStore(path)
    restored = s2.get("alert-demo-critical-001")
    assert restored is not None
    assert restored.acknowledged is True
    assert restored.acknowledge_note == "kept across restart"
    assert s2.count() == before
    assert s2.metrics().acknowledged_alerts >= 1
    s2.close()


def test_duplicate_kafka_delivery_does_not_duplicate_alert(tmp_path: Path) -> None:
    path = tmp_path / "dedupe.db"
    store = DurableAlertStore(path)
    alert = _alert("alert-k-1")
    a1, inserted1 = store.ingest_kafka(alert, idempotency_key="alerts:0:1")
    a2, inserted2 = store.ingest_kafka(alert, idempotency_key="alerts:0:1")
    assert inserted1 is True
    assert inserted2 is False
    assert a1.alert_id == a2.alert_id
    assert store.count() == 1
    # Same alert_id, different kafka offset → upsert, still one row
    store.ingest_kafka(alert, idempotency_key="alerts:0:2")
    assert store.count() == 1
    store.close()


def test_metrics_not_truncated_at_10000(tmp_path: Path) -> None:
    path = tmp_path / "metrics.db"
    store = DurableAlertStore(path)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # Insert more than the old silent 10k list cap
    n = 10_050
    with store._lock:
        for i in range(n):
            alert = AlertRecord(
                alert_id=f"a-{i}",
                patient_id="Patient/p",
                indicator="sofa-deterioration",
                event_time=base + timedelta(seconds=i),
                score=2,
                tier="watch",
                completeness="complete",
                routing="passive",
            )
            store._write_alert(alert, action="bulk")
        store._conn.commit()
    m = store.metrics()
    assert m.total_alerts == n
    assert m.by_tier.get("watch") == n
    store.close()


def test_list_pagination_bounded(tmp_path: Path) -> None:
    path = tmp_path / "page.db"
    store = DurableAlertStore(path)
    for i in range(5):
        store.upsert(_alert(f"p-{i}", minutes=i))
    page = store.list(limit=2, offset=0)
    assert len(page) == 2
    page2 = store.list(limit=2, offset=2)
    assert len(page2) == 2
    assert {a.alert_id for a in page}.isdisjoint({a.alert_id for a in page2})
    store.close()


def test_restart_preserves_episode_ids(tmp_path: Path) -> None:
    path = tmp_path / "episode-ids.db"
    s1 = DurableAlertStore(path)
    s1.upsert(_alert("alert-ep-1", minutes=2))
    s1.upsert(_alert("alert-ep-2", minutes=1))
    before = {e.episode_id for e in s1.list_episodes(patient_id="Patient/p-1")}
    assert len(before) == 1
    s1.close()

    s2 = DurableAlertStore(path)
    after = {e.episode_id for e in s2.list_episodes(patient_id="Patient/p-1")}
    assert before == after
    s2.close()


def test_memory_metrics_also_untruncated() -> None:
    store = MemoryAlertStore()
    for i in range(120):
        store.upsert(_alert(f"m-{i}", minutes=i))
    assert store.metrics().total_alerts == 120
    assert store.count() == 120
