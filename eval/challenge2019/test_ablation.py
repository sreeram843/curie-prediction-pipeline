"""Ablation variant construction (no archive)."""

from __future__ import annotations

from eval.challenge2019.ablation import ablation_variants, knob_signature, load_frozen_knobs


def test_winner_knobs_load() -> None:
    knobs = load_frozen_knobs()
    assert knobs["page_gate_enabled"] is True
    assert knobs["resolved_bundle"]


def test_drop_baseline_is_null_on_winner() -> None:
    variants = dict(ablation_variants())
    primary = knob_signature(variants["primary_operating_point"])
    assert knob_signature(variants["drop_baseline"]) == primary


def test_drop_refractory_and_page_gate_change_policy() -> None:
    variants = dict(ablation_variants())
    primary = knob_signature(variants["primary_operating_point"])
    assert knob_signature(variants["drop_refractory"]) != primary
    assert knob_signature(variants["drop_page_gate"]) != primary
    assert variants["drop_refractory"]["refractory_minutes"] == 0
    assert variants["drop_page_gate"]["page_gate_enabled"] is False
