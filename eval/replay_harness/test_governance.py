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


def test_component_resolution_gap_minutes_overrides_blanket_gap() -> None:
    """A component charted sparsely by nature (e.g. liver/bilirubin) shouldn't
    lose its trajectory just because 90 minutes passed with no new reading --
    but a component with no override still resets on the same 90-minute gap."""
    base_alert = {
        "score": 4,
        "tier": "urgent",
        "event_time": "2024-01-01T00:00:00+00:00",
        "patient_id": "Patient/1",
        "component_breakdown": {"liver": 3},
    }
    second_alert = {**base_alert, "event_time": "2024-01-01T01:30:00+00:00"}  # +90 min

    # Blanket 60-minute gap, no override: 90-minute silence resets the streak.
    blanket_config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=2,
        baseline_enabled=False,
        refractory_minutes=0,
        resolution_gap_minutes=60,
    )
    blanket_state = PatientGovState()
    evaluate(base_alert, blanket_state, blanket_config)
    evaluate(second_alert, blanket_state, blanket_config)
    assert blanket_state.crossings_above_threshold == 1  # reset, started over

    # Same 90-minute gap, but liver gets a 120-minute allowance: streak survives.
    override_config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=2,
        baseline_enabled=False,
        refractory_minutes=0,
        resolution_gap_minutes=60,
        component_resolution_gap_minutes={"liver": 120},
    )
    override_state = PatientGovState()
    evaluate(base_alert, override_state, override_config)
    evaluate(second_alert, override_state, override_config)
    assert override_state.crossings_above_threshold == 2  # survived, confirmed


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


def test_late_out_of_order_does_not_mutate_or_emit() -> None:
    config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=False,
    )
    state = PatientGovState()
    first = evaluate(
        {
            "score": 5,
            "tier": "urgent",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "Patient/1",
            "positive_components": 3,
        },
        state,
        config,
    )
    assert first.emit is True
    crossings = state.crossings_above_threshold
    late = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T00:30:00+00:00",
            "patient_id": "Patient/1",
            "positive_components": 3,
        },
        state,
        config,
    )
    assert late.emit is False
    assert late.reason == "late_out_of_order"
    assert state.crossings_above_threshold == crossings


def test_late_passive_correction_is_emitted_without_mutating_trajectory() -> None:
    config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=False,
        late_event_policy="passive_correction",
    )
    state = PatientGovState()
    first = evaluate(
        {
            "score": 5,
            "tier": "urgent",
            "event_time": "2024-01-01T01:00:00+00:00",
            "patient_id": "Patient/1",
        },
        state,
        config,
    )
    assert first.emit is True
    before = (state.last_processed_event_time, state.crossings_above_threshold)

    late = evaluate(
        {
            "score": 8,
            "tier": "critical",
            "event_time": "2024-01-01T00:30:00+00:00",
            "patient_id": "Patient/1",
        },
        state,
        config,
    )
    assert late.emit is True
    assert late.reason == "late_correction"
    assert late.routing == "passive"
    assert late.alert["late_correction"] is True
    assert late.alert["suppressed"] is False
    assert (state.last_processed_event_time, state.crossings_above_threshold) == before


def test_arrival_order_permutations_same_emitted_ids() -> None:
    """Ordered event-times yield a stable emit sequence; late arrivals are dropped."""
    config = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=True,
        page_min_crossings=2,
        page_trajectory_persistence_minutes=0,
        page_min_score_delta=0,
        page_min_positive_components=0,
    )
    base = [
        {
            "score": 4,
            "tier": "urgent",
            "event_time": "2024-01-01T00:00:00+00:00",
            "patient_id": "P",
        },
        {
            "score": 5,
            "tier": "urgent",
            "event_time": "2024-01-01T00:10:00+00:00",
            "patient_id": "P",
        },
        {
            "score": 6,
            "tier": "urgent",
            "event_time": "2024-01-01T00:20:00+00:00",
            "patient_id": "P",
        },
    ]

    def run(order: list[dict]) -> list[tuple[str, str]]:
        state = PatientGovState()
        out: list[tuple[str, str]] = []
        for alert in order:
            d = evaluate(dict(alert), state, config)
            if d.emit:
                out.append((alert["event_time"], d.routing))
        return out

    chronological = run(base)
    assert chronological == [
        ("2024-01-01T00:00:00+00:00", "passive"),
        ("2024-01-01T00:10:00+00:00", "interruptive"),
        ("2024-01-01T00:20:00+00:00", "interruptive"),
    ]
    # Newer-first then older: older is late_out_of_order and must not appear
    scrambled = [base[1], base[0], base[2]]
    scrambled_result = run(scrambled)
    assert scrambled_result[0] == ("2024-01-01T00:10:00+00:00", "passive")
    assert all(t != "2024-01-01T00:00:00+00:00" for t, _ in scrambled_result)
