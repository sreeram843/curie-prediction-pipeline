"""Tests for CURIE-032/033 governance extensions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eval.replay_harness.governance import GovernanceConfig, PatientGovState, evaluate


def _alert(**kwargs):
    base = {
        "score": 4,
        "tier": "urgent",
        "event_time": datetime(2024, 6, 1, 12, 0, tzinfo=UTC).isoformat(),
        "positive_components": 2,
        "component_breakdown": [
            {"name": "respiration", "points": 2},
            {"name": "cardiovascular", "points": 2},
        ],
    }
    base.update(kwargs)
    return base


def test_component_delta_identifies_newly_worsened() -> None:
    cfg = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=True,
        page_min_crossings=1,
        page_trajectory_persistence_minutes=0,
        page_min_score_delta=0,
        page_min_newly_worsened_components=1,
    )
    state = PatientGovState()
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    first = evaluate(
        _alert(
            event_time=t0.isoformat(),
            component_breakdown=[
                {"name": "respiration", "points": 1},
                {"name": "cardiovascular", "points": 1},
            ],
        ),
        state,
        cfg,
    )
    assert first.emit is True
    # Second alert: respiration newly worsens → interruptive allowed
    second = evaluate(
        _alert(
            event_time=(t0 + timedelta(minutes=10)).isoformat(),
            score=6,
            tier="critical",
            component_breakdown=[
                {"name": "respiration", "points": 3},
                {"name": "cardiovascular", "points": 1},
            ],
            component_evidence={"respiration": ["Observation/rr-1"]},
        ),
        state,
        cfg,
    )
    assert second.routing == "interruptive"
    assert "respiration" in second.alert["newly_worsened_components"]
    assert second.alert["newly_worsened_evidence"]["respiration"] == ["Observation/rr-1"]


def test_component_delta_defers_without_worsening() -> None:
    cfg = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=True,
        page_min_crossings=1,
        page_trajectory_persistence_minutes=0,
        page_min_score_delta=0,
        page_min_newly_worsened_components=1,
    )
    state = PatientGovState()
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    evaluate(
        _alert(
            event_time=t0.isoformat(),
            component_breakdown=[{"name": "respiration", "points": 2}],
        ),
        state,
        cfg,
    )
    again = evaluate(
        _alert(
            event_time=(t0 + timedelta(minutes=5)).isoformat(),
            component_breakdown=[{"name": "respiration", "points": 2}],
        ),
        state,
        cfg,
    )
    assert again.routing == "passive"
    assert again.alert["page_deferred_reason"] == "page_component_delta"


def test_quality_gate_stale_defers_page_not_llm() -> None:
    cfg = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=False,
        quality_gate_enabled=True,
        quality_max_data_age_minutes=60,
    )
    state = PatientGovState()
    d = evaluate(_alert(data_age_minutes=120), state, cfg)
    assert d.emit is True
    assert d.routing == "passive"
    assert d.alert["page_deferred_reason"] == "quality_stale"


def test_legacy_frozen_policy_still_works_without_new_gates() -> None:
    """Old policy version: page_gate off, no quality — interruptive by tier."""
    cfg = GovernanceConfig(
        trajectory_persistence_minutes=0,
        min_crossings=1,
        baseline_enabled=False,
        refractory_minutes=0,
        page_gate_enabled=False,
        quality_gate_enabled=False,
    )
    d = evaluate(_alert(), PatientGovState(), cfg)
    assert d.routing == "interruptive"
    assert d.reason == "pass"
