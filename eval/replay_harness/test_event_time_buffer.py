"""CURIE-006: event-time buffer permutation / lateness / restart tests."""

from __future__ import annotations

from itertools import permutations

from eval.replay_harness.event_time_buffer import EventTimeBuffer
from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate


def _process_order(
    order: list[tuple[int, str, dict]],
    *,
    allowed_lateness_ms: int = 30 * 60 * 1000,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (emitted routing pairs by alert id, late tie-breakers)."""
    buf: EventTimeBuffer[dict] = EventTimeBuffer(allowed_lateness_ms=allowed_lateness_ms)
    state = PatientGovState()
    config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=False,
    )
    emitted: list[tuple[str, str]] = []
    late_ids: list[str] = []

    def apply(payload: dict) -> None:
        d = evaluate(dict(payload), state, config)
        if d.emit:
            emitted.append((payload["alert_id"], d.routing))

    for et, tie, payload in order:
        result = buf.offer(et, payload, tie_breaker=tie)
        for late in result.late:
            late_ids.append(late.tie_breaker)
        for ready in result.ready:
            apply(ready.payload)

    for ready in buf.close().ready:
        apply(ready.payload)
    return emitted, late_ids


def test_permutations_within_lateness_same_emits() -> None:
    events = [
        (
            1_000,
            "a",
            {
                "alert_id": "a",
                "score": 4,
                "tier": "urgent",
                "event_time": "2024-01-01T00:00:01+00:00",
                "patient_id": "P",
            },
        ),
        (
            2_000,
            "b",
            {
                "alert_id": "b",
                "score": 5,
                "tier": "urgent",
                "event_time": "2024-01-01T00:00:02+00:00",
                "patient_id": "P",
            },
        ),
        (
            3_000,
            "c",
            {
                "alert_id": "c",
                "score": 6,
                "tier": "urgent",
                "event_time": "2024-01-01T00:00:03+00:00",
                "patient_id": "P",
            },
        ),
    ]
    results = [
        _process_order(list(p), allowed_lateness_ms=60_000)[0] for p in permutations(events)
    ]
    assert all(r == results[0] for r in results)
    assert [aid for aid, _ in results[0]] == ["a", "b", "c"]


def test_beyond_lateness_is_dropped() -> None:
    buf: EventTimeBuffer[str] = EventTimeBuffer(allowed_lateness_ms=1_000)
    r1 = buf.offer(10_000, "new", tie_breaker="n")
    assert not r1.late
    r2 = buf.offer(8_000, "old", tie_breaker="o")
    assert len(r2.late) == 1
    assert r2.late[0].tie_breaker == "o"
    assert r2.disposition_late == "late_beyond_lateness"


def test_equal_timestamp_uses_tie_breaker() -> None:
    buf: EventTimeBuffer[str] = EventTimeBuffer(allowed_lateness_ms=60_000)
    buf.offer(5_000, "second", tie_breaker="b")
    buf.offer(5_000, "first", tie_breaker="a")
    # Still within lateness window until close
    assert buf.snapshot_pending()
    flushed = buf.close().ready
    assert [e.payload for e in flushed] == ["first", "second"]


def test_duplicate_tie_breakers_preserve_offer_order() -> None:
    buf: EventTimeBuffer[str] = EventTimeBuffer(allowed_lateness_ms=60_000)
    buf.offer(1_000, "x", tie_breaker="same")
    buf.offer(1_000, "y", tie_breaker="same")
    assert [e.payload for e in buf.close().ready] == ["x", "y"]


def test_restart_restore_pending_same_flush() -> None:
    buf: EventTimeBuffer[str] = EventTimeBuffer(allowed_lateness_ms=5_000)
    buf.offer(10_000, "a", tie_breaker="a")
    buf.offer(11_000, "b", tie_breaker="b")
    snap = buf.snapshot_pending()

    restored: EventTimeBuffer[str] = EventTimeBuffer(allowed_lateness_ms=5_000)
    restored.restore_pending(snap)
    assert [e.payload for e in restored.close().ready] == ["a", "b"]
