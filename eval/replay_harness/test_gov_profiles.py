"""apply_gov_knobs() config mapping — previously untested."""

from __future__ import annotations

from eval.replay_harness.gov_profiles import apply_gov_knobs

_BASE_KNOBS = {
    "trajectory_persistence_minutes": 0,
    "min_crossings": 1,
    "baseline_enabled": False,
    "refractory_minutes": 90,
    "min_components_required": 1,
    "naive_threshold": 2,
}


def test_resolution_gap_minutes_defaults_to_60_when_unset() -> None:
    """Regression: resolution_gap_minutes existed on GovernanceConfig but was
    never mapped from the knobs dict, so no candidate/ablation in the study
    could ever actually change it -- it silently stayed at the dataclass
    default regardless of what knobs were passed."""
    _, cfg, _ = apply_gov_knobs({}, _BASE_KNOBS)
    assert cfg.resolution_gap_minutes == 60


def test_resolution_gap_minutes_honors_explicit_knob() -> None:
    _, cfg, _ = apply_gov_knobs({}, {**_BASE_KNOBS, "resolution_gap_minutes": 240})
    assert cfg.resolution_gap_minutes == 240


def test_component_resolution_gap_minutes_honors_explicit_knob() -> None:
    _, cfg, _ = apply_gov_knobs(
        {},
        {**_BASE_KNOBS, "component_resolution_gap_minutes": {"liver": 240, "respiration": 240}},
    )
    assert cfg.component_resolution_gap_minutes == {"liver": 240, "respiration": 240}


def test_component_resolution_gap_minutes_defaults_empty() -> None:
    _, cfg, _ = apply_gov_knobs({}, _BASE_KNOBS)
    assert cfg.component_resolution_gap_minutes == {}
