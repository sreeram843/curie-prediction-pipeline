"""Canonical golden SOFA fixtures — shared contract for Python + Java scorers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eval.indicators.registry import load_rule_bundle
from eval.sofa.scoring import (
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)

GOLDEN = Path(__file__).resolve().parent / "golden" / "sofa_cases.v0.2.json"
T0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


def _load() -> dict:
    return json.loads(GOLDEN.read_text())


def _inputs_from_case(case: dict) -> list[SofaComponentInput]:
    raw = case["inputs"]
    out: list[SofaComponentInput] = []
    for name in SofaComponentName:
        if name.value not in raw:
            continue
        out.append(SofaComponentInput.model_validate({"name": name.value, **raw[name.value]}))
    return out


def test_golden_file_targets_latest_sofa_bundle() -> None:
    data = _load()
    bundle = load_rule_bundle("sepsis-sofa")
    assert data["rule_bundle_id"] == bundle["bundle_id"]
    assert data["rule_version"] == bundle["version"]


@pytest.mark.parametrize("case", _load()["cases"], ids=lambda c: c["id"])
def test_golden_sofa_case(case: dict) -> None:
    data = _load()
    bundle = load_rule_bundle("sepsis-sofa")
    result = compute_sofa_score(
        patient_id=f"Patient/golden-{case['id']}",
        event_time=T0,
        inputs=_inputs_from_case(case),
        rule_bundle_id=data["rule_bundle_id"],
        rule_version=data["rule_version"],
        rule_bundle=bundle,
    )
    expect = case["expect"]
    assert result.total_score == expect["total_score"]
    assert result.completeness.value == expect["completeness"]
    assert [m.value for m in result.missing_components] == expect["missing"]
    assert tier_for_score(result.total_score).value == expect["tier"]
    for name, pts in (expect.get("component_points") or {}).items():
        comp = next(c for c in result.components if c.name.value == name)
        assert comp.points == pts
