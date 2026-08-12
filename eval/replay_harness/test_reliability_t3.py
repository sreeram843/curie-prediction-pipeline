"""T3-lite reliability cases: duplicates, recovery reset, encounter change."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eval.replay_harness.governance import (
    GovernanceConfig,
    PatientGovState,
    evaluate,
    note_below_threshold,
)
from eval.sofa.scoring import SofaComponentInput, SofaComponentName
from eval.sofa.stream_scorer import PatientState


def test_duplicate_idempotency_key_ignored() -> None:
    state = PatientState()
    assert state.seen("obs-1") is False
    assert state.seen("obs-1") is True


def test_stale_event_time_does_not_overwrite() -> None:
    state = PatientState()
    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    newer = SofaComponentInput(
        name=SofaComponentName.COAGULATION, platelets_10e9_l=40, evidence_ids=["a"]
    )
    older = SofaComponentInput(
        name=SofaComponentName.COAGULATION, platelets_10e9_l=10, evidence_ids=["b"]
    )
    assert state.apply(newer, t1) is True
    assert state.apply(older, t0) is False
    assert state.latest[SofaComponentName.COAGULATION].platelets_10e9_l == 40


def test_encounter_change_resets_features() -> None:
    state = PatientState()
    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    state.set_encounter("Encounter/1")
    state.apply(
        SofaComponentInput(
            name=SofaComponentName.RENAL, creatinine_mg_dl=3.0, evidence_ids=["c"]
        ),
        t0,
    )
    state.set_encounter("Encounter/2")
    assert SofaComponentName.RENAL not in state.latest


def test_governance_duplicate_same_event_time_counts_once() -> None:
    config = GovernanceConfig(baseline_enabled=False, min_crossings=2)
    state = PatientGovState()
    t = "2024-01-01T08:00:00+00:00"
    a = {"score": 7, "tier": "critical", "event_time": t, "patient_id": "p"}
    evaluate(a, state, config)
    evaluate(a, state, config)
    assert state.crossings_above_threshold == 1


def test_governance_recovery_resets_trajectory() -> None:
    config = GovernanceConfig(
        baseline_enabled=False,
        min_crossings=2,
        trajectory_persistence_minutes=30,
    )
    state = PatientGovState()
    t0 = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    evaluate(
        {
            "score": 7,
            "tier": "critical",
            "event_time": t0.isoformat(),
            "patient_id": "p",
        },
        state,
        config,
    )
    evaluate(
        {
            "score": 7,
            "tier": "critical",
            "event_time": (t0 + timedelta(minutes=35)).isoformat(),
            "patient_id": "p",
        },
        state,
        config,
    )
    assert state.crossings_above_threshold >= 2
    note_below_threshold(state)
    assert state.crossings_above_threshold == 0
    # Re-deteriorate must re-accumulate
    d = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": (t0 + timedelta(minutes=40)).isoformat(),
            "patient_id": "p",
        },
        state,
        config,
    )
    assert d.emit is False
    assert d.reason == "trajectory_not_met"
