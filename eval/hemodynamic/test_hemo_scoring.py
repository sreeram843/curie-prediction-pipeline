"""CURIE-036 hemodynamic indicator tests."""

from __future__ import annotations

from datetime import UTC, datetime

from eval.hemodynamic.scoring import HemoInput, compute_hemo_score, tier_for_hemo_score
from eval.indicators.plugin import dispatch_score, list_plugins
from eval.indicators.registry import validate_activation


def test_hemo_plugin_registered_and_activation() -> None:
    plugins = {p.score_type: p for p in list_plugins()}
    assert "hemo_shock" in plugins
    assert plugins["hemo_shock"].scorer_attr == "compute_hemo_score"
    assert "HemoScorer" in (plugins["hemo_shock"].runtime_impl.get("java") or "")
    assert callable(dispatch_score("hemo_shock"))
    report = validate_activation()
    assert report["ok"] is True
    assert "hemo-shock" in report["active"]


def test_hemo_score_cases() -> None:
    t0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    r = compute_hemo_score(
        patient_id="Patient/1",
        event_time=t0,
        inputs=HemoInput(lactate_mmol_l=2.5, map_mmhg=60.0),
    )
    assert r.stage == 2
    assert r.total_score == 4
    assert r.clinical_claim == "surveillance_indicator_not_diagnosis"
    assert tier_for_hemo_score(4).value == "urgent"
