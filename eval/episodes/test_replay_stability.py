"""CURIE-028: replay-stable episode identity and monotonic timestamps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from action.api.app.durable_store import DurableAlertStore
from eval.episodes.arbiter import EpisodeArbiter, signal_ref_from_alert


def _alert(
    *,
    alert_id: str,
    indicator: str,
    tier: str,
    score: int,
    event_time: datetime,
    routing: str = "interruptive",
) -> dict:
    return {
        "alert_id": alert_id,
        "patient_id": "Patient/replay-1",
        "encounter_id": "Encounter/1",
        "indicator": indicator,
        "tier": tier,
        "score": score,
        "routing": routing,
        "event_time": event_time,
        "evidence_ids": [f"Observation/{alert_id}"],
        "signal": {
            "signal_type": indicator,
            "severity": tier,
            "score": score,
            "evidence_ids": [f"Observation/{alert_id}"],
        },
    }


def test_in_order_and_reverse_order_same_episode_id() -> None:
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=10)
    a = _alert(
        alert_id="sig-a",
        indicator="sofa-deterioration",
        tier="urgent",
        score=4,
        event_time=t0,
    )
    b = _alert(
        alert_id="sig-b",
        indicator="aki",
        tier="urgent",
        score=4,
        event_time=t1,
    )

    forward = EpisodeArbiter()
    r1 = forward.ingest(a)
    r2 = forward.ingest(b)
    assert r1.episode.episode_id == r2.episode.episode_id

    reverse = EpisodeArbiter()
    r3 = reverse.ingest(b)
    r4 = reverse.ingest(a)
    assert r3.episode.episode_id == r4.episode.episode_id
    assert r2.episode.episode_id == r4.episode.episode_id
    assert r4.episode.opened_at == t0
    assert r4.episode.opened_at <= r4.episode.updated_at


def test_duplicate_ingest_does_not_open_second_episode() -> None:
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    a = _alert(
        alert_id="sig-dup",
        indicator="sofa-deterioration",
        tier="urgent",
        score=4,
        event_time=t0,
    )
    arb = EpisodeArbiter()
    first = arb.ingest(a)
    second = arb.ingest(a)
    assert first.episode.episode_id == second.episode.episode_id
    assert second.reason == "duplicate_signal_id"
    assert len(arb.list_all()) == 1


def test_updated_at_never_regresses_on_older_signal() -> None:
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=30)
    newer = _alert(
        alert_id="newer",
        indicator="sofa-deterioration",
        tier="urgent",
        score=4,
        event_time=t1,
    )
    older = _alert(
        alert_id="older",
        indicator="aki",
        tier="watch",
        score=2,
        event_time=t0,
        routing="passive",
    )
    arb = EpisodeArbiter()
    arb.ingest(newer)
    after = arb.ingest(older)
    assert after.episode.updated_at == t1
    assert after.episode.opened_at == t0
    assert after.episode.opened_at <= after.episode.updated_at
    times = [s.event_time for s in after.episode.signals]
    assert times == sorted(times)


def test_restart_via_durable_store_keeps_episode_id(tmp_path: Path) -> None:
    path = tmp_path / "episodes.sqlite"
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    from action.api.app.models import AlertRecord

    alert = AlertRecord(
        alert_id="durable-1",
        patient_id="Patient/replay-1",
        encounter_id="Encounter/1",
        indicator="sofa-deterioration",
        event_time=t0,
        score=4,
        tier="urgent",
        completeness="complete",
        routing="interruptive",
        rule_bundle_id="sepsis-sofa",
        rule_version="0.3.0",
    )
    s1 = DurableAlertStore(path)
    s1.upsert(alert)
    before = {e.episode_id for e in s1.list_episodes(patient_id="Patient/replay-1")}
    assert len(before) == 1
    s1.close()

    s2 = DurableAlertStore(path)
    after = {e.episode_id for e in s2.list_episodes(patient_id="Patient/replay-1")}
    assert before == after
    s2.close()


def test_signal_ref_roundtrip_for_stability_helpers() -> None:
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    ref = signal_ref_from_alert(
        _alert(
            alert_id="x",
            indicator="respiratory-deterioration",
            tier="urgent",
            score=4,
            event_time=t0,
        )
    )
    assert ref.signal_id == "x"
    assert ref.event_time == t0
