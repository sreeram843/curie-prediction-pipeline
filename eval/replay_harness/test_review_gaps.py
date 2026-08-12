"""Parity + review-gap coverage: governance, alert ids, validation, idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate
from eval.sofa.alert_ids import alert_id
from eval.sofa.stream_scorer import IdempotencyCache, observation_to_input


def test_alert_context_flags_suppress() -> None:
    config = GovernanceConfig(
        baseline_enabled=False, min_crossings=1, trajectory_persistence_minutes=0
    )
    state = PatientGovState()
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "p",
            "context_flags": ["comfort_care"],
        },
        state,
        config,
    )
    assert d.emit is False
    assert d.reason.startswith("context:")
    assert "comfort_care" in state.context_flags


def test_context_flags_clear_on_encounter_change() -> None:
    config = GovernanceConfig(
        baseline_enabled=False, min_crossings=1, trajectory_persistence_minutes=0
    )
    state = PatientGovState()
    evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "p",
            "encounter_id": "Encounter/1",
            "context_flags": ["comfort_care"],
        },
        state,
        config,
    )
    assert "comfort_care" in state.context_flags
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-02-01T01:00:00+00:00",
            "patient_id": "p",
            "encounter_id": "Encounter/2",
        },
        state,
        config,
    )
    assert "comfort_care" not in state.context_flags
    assert d.emit is True
    assert d.reason == "pass"


def test_context_flags_do_not_leak_from_unset_encounter_into_first() -> None:
    """Flags set before any encounter_id must not suppress the first named encounter."""
    config = GovernanceConfig(
        baseline_enabled=False, min_crossings=1, trajectory_persistence_minutes=0
    )
    state = PatientGovState()
    evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "p",
            "context_flags": ["comfort_care"],
        },
        state,
        config,
    )
    assert "comfort_care" in state.context_flags
    assert state.encounter_id is None
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T02:00:00+00:00",
            "patient_id": "p",
            "encounter_id": "Encounter/1",
        },
        state,
        config,
    )
    assert "comfort_care" not in state.context_flags
    assert state.encounter_id == "Encounter/1"
    assert d.emit is True
    assert d.reason == "pass"


def test_context_flags_sticky_within_same_encounter() -> None:
    config = GovernanceConfig(
        baseline_enabled=False, min_crossings=1, trajectory_persistence_minutes=0
    )
    state = PatientGovState()
    evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "p",
            "encounter_id": "Encounter/1",
            "context_flags": ["comfort_care"],
        },
        state,
        config,
    )
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T03:00:00+00:00",
            "patient_id": "p",
            "encounter_id": "Encounter/1",
        },
        state,
        config,
    )
    assert "comfort_care" in state.context_flags
    assert d.emit is False
    assert d.reason.startswith("context:")


def test_below_threshold_resets_trajectory() -> None:
    config = GovernanceConfig(
        baseline_enabled=False, min_crossings=2, trajectory_persistence_minutes=0
    )
    state = PatientGovState()
    evaluate(
        {
            "score": 5,
            "tier": "urgent",
            "event_time": "2024-01-01T00:00:00+00:00",
            "patient_id": "p",
        },
        state,
        config,
    )
    assert state.crossings_above_threshold == 1
    d = evaluate(
        {
            "score": 1,
            "tier": "none",
            "event_time": "2024-01-01T00:10:00+00:00",
            "patient_id": "p",
        },
        state,
        config,
    )
    assert d.reason == "below_threshold"
    assert state.crossings_above_threshold == 0


def test_canonical_alert_id_stable() -> None:
    a = alert_id("Patient/1", "Encounter/9", "sepsis", 7, 1_700_000_000_000, "0.2.0")
    b = alert_id("Patient/1", "Encounter/9", "sepsis", 7, 1_700_000_000_000, "0.2.0")
    assert a == b
    assert a.startswith("alert-")


def test_observation_rejects_bad_status_and_unit() -> None:
    bad_status = {
        "resourceType": "Observation",
        "status": "cancelled",
        "code": {"coding": [{"code": "777-3"}]},
        "valueQuantity": {"value": 40, "unit": "10*9/L"},
    }
    assert observation_to_input(bad_status) is None
    bad_unit = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"code": "777-3"}]},
        "valueQuantity": {"value": 40, "unit": "g/dL"},
    }
    assert observation_to_input(bad_unit) is None
    ok = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": [{"code": "777-3"}]},
        "valueQuantity": {"value": 150000, "unit": "/uL"},
    }
    mapped = observation_to_input(ok)
    assert mapped is not None
    assert mapped.platelets_10e9_l == 150.0


def test_idempotency_ttl_and_capacity_not_full_clear() -> None:
    cache = IdempotencyCache(ttl=timedelta(seconds=1), max_keys=3)
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    assert cache.seen("a", t0) is False
    assert cache.seen("a", t0 + timedelta(milliseconds=100)) is True
    assert cache.seen("a", t0 + timedelta(seconds=2)) is False  # expired
    assert cache.seen("b", t0) is False
    assert cache.seen("c", t0) is False
    assert cache.seen("d", t0) is False  # evicts eldest
    assert cache.seen("b", t0 + timedelta(milliseconds=10)) is True
