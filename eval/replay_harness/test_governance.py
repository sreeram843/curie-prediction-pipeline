"""Governance unit tests + alert-reduction ratio helper."""

from __future__ import annotations

from eval.replay_harness.governance import (
    GovernanceConfig,
    PatientGovState,
    alert_reduction_ratio,
    evaluate,
)


def test_trajectory_and_reduction_ratio() -> None:
    config = GovernanceConfig(
        trajectory_persistence_minutes=30,
        min_crossings=2,
        baseline_enabled=False,
        refractory_minutes=120,
    )
    state = PatientGovState()
    naive = 0
    governed = 0
    times = [
        "2024-01-01T00:00:00+00:00",
        "2024-01-01T00:10:00+00:00",
        "2024-01-01T00:35:00+00:00",
        "2024-01-01T00:40:00+00:00",
    ]
    for t in times:
        alert = {
            "score": 5,
            "tier": "urgent",
            "event_time": t,
            "patient_id": "Patient/1",
        }
        naive += 1
        decision = evaluate(alert, state, config)
        if decision.emit:
            governed += 1
    assert governed == 1
    assert alert_reduction_ratio(naive, governed) == 0.25


def test_page_gate_downgrades_interruptive_to_watch() -> None:
    """Watch fires on light gates; page waits for rising score + extra crossing."""
    config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=True,
        page_min_crossings=2,
        page_trajectory_persistence_minutes=0,
        page_min_score_delta=1,
        page_min_positive_components=0,
    )
    state = PatientGovState()
    first = evaluate(
        {
            "score": 4,
            "tier": "urgent",
            "event_time": "2024-01-01T00:00:00+00:00",
            "patient_id": "Patient/1",
        },
        state,
        config,
    )
    assert first.emit is True
    assert first.routing == "passive"
    assert first.reason == "pass_watch:page_crossings"

    second = evaluate(
        {
            "score": 5,
            "tier": "urgent",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "Patient/1",
        },
        state,
        config,
    )
    assert second.emit is True
    assert second.routing == "interruptive"
    assert second.reason == "pass"


def test_page_gate_requires_positive_components() -> None:
    config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=True,
        page_min_crossings=1,
        page_trajectory_persistence_minutes=0,
        page_min_score_delta=0,
        page_min_positive_components=2,
    )
    state = PatientGovState()
    d = evaluate(
        {
            "score": 5,
            "tier": "urgent",
            "event_time": "2024-01-01T00:00:00+00:00",
            "patient_id": "Patient/1",
            "positive_components": 1,
        },
        state,
        config,
    )
    assert d.emit is True
    assert d.routing == "passive"
    assert d.alert.get("page_deferred_reason") == "page_components"
