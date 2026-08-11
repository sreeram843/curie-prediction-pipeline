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
