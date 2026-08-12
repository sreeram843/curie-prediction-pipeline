"""Prove changing bundle params changes scores (JSON is authoritative)."""

from __future__ import annotations

from datetime import UTC, datetime

from eval.indicators.registry import load_rule_bundle
from eval.sofa.scoring import SofaComponentInput, SofaComponentName, compute_sofa_score
from eval.sofa.thresholds import SofaThresholds

T0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


def test_bundle_params_change_respiration_cutoff() -> None:
    bundle = load_rule_bundle("sepsis-sofa")
    base = SofaThresholds.from_bundle(bundle)
    assert base.resp_p2_lt == 300

    mutated = dict(bundle)
    score = dict(mutated["score"])
    ct = dict(score["component_thresholds"])
    resp = dict(ct["respiration"])
    params = dict(resp.get("params") or {})
    params["p2_ratio_lt"] = 250  # stricter: ratio 260 no longer scores 2
    resp["params"] = params
    ct["respiration"] = resp
    score["component_thresholds"] = ct
    mutated["score"] = score

    inputs = [
        SofaComponentInput(
            name=SofaComponentName.RESPIRATION,
            pao2_fio2=260,
            mechanically_ventilated=False,
        ),
        SofaComponentInput(name=SofaComponentName.COAGULATION, platelets_10e9_l=200),
        SofaComponentInput(name=SofaComponentName.LIVER, bilirubin_mg_dl=0.8),
        SofaComponentInput(name=SofaComponentName.CARDIOVASCULAR, map_mmhg=80),
        SofaComponentInput(name=SofaComponentName.CNS, gcs=15),
        SofaComponentInput(name=SofaComponentName.RENAL, creatinine_mg_dl=0.9),
    ]
    default = compute_sofa_score(
        patient_id="Patient/th-default",
        event_time=T0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0",
        rule_bundle=bundle,
    )
    tight = compute_sofa_score(
        patient_id="Patient/th-tight",
        event_time=T0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0",
        rule_bundle=mutated,
    )
    assert default.total_score == 2
    assert tight.total_score == 1
