"""CURIE-005: Python governance extraction matches shared parity fixture."""

from __future__ import annotations

import json
from pathlib import Path

from eval.indicators.registry import (
    governance_config_from_bundle,
    governance_dataclass_from_bundle,
    load_rule_bundle,
)

PARITY = Path(__file__).resolve().parent / "golden" / "governance_parity.v1.json"


def test_parity_fixture_extraction() -> None:
    data = json.loads(PARITY.read_text())
    knobs = governance_config_from_bundle(data["bundle"])
    expect = data["expect"]
    for key, value in expect.items():
        got = knobs[key]
        if isinstance(value, list):
            assert set(got) == set(value), key
        else:
            assert got == value, key


def test_empty_governance_uses_documented_defaults() -> None:
    knobs = governance_config_from_bundle({"governance": {}})
    assert knobs["trajectory_persistence_minutes"] == 30
    assert knobs["min_crossings"] == 2
    assert knobs["baseline_enabled"] is True
    assert knobs["baseline_lookback_hours"] == 24
    assert knobs["refractory_minutes"] == 120
    assert knobs["resolution_gap_minutes"] == 60
    assert knobs["page_gate_enabled"] is False
    assert knobs["page_min_crossings"] == 2
    assert knobs["page_min_positive_components"] == 0


def test_sepsis_v030_replay_uses_page_gate() -> None:
    bundle = load_rule_bundle("sepsis-sofa", "0.3.0")
    cfg = governance_dataclass_from_bundle(bundle)
    assert cfg.page_gate_enabled is True
    assert cfg.baseline_enabled is False
    assert cfg.min_crossings == 1
    assert cfg.trajectory_persistence_minutes == 0
    assert cfg.page_min_positive_components == 2
    assert cfg.resolution_gap_minutes == 60


def test_aki_v030_page_gate_present() -> None:
    bundle = load_rule_bundle("aki-kdigo", "0.3.0")
    cfg = governance_dataclass_from_bundle(bundle)
    assert cfg.page_gate_enabled is True
    assert cfg.page_min_positive_components == 1


def test_scenario_override_is_explicit() -> None:
    bundle = load_rule_bundle("aki-kdigo", "0.3.0")
    full = governance_dataclass_from_bundle(bundle)
    assert full.baseline_enabled is True
    demo = governance_dataclass_from_bundle(
        bundle, overrides={"baseline_enabled": False}
    )
    assert demo.baseline_enabled is False
    assert demo.page_gate_enabled is True
