"""T0 golden fixtures for SOFA scoring — mechanical correctness only."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eval.sofa.scoring import (
    AcuityTier,
    ScoreCompleteness,
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)

T0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


def _full_mild() -> list[SofaComponentInput]:
    return [
        SofaComponentInput(
            name=SofaComponentName.RESPIRATION,
            pao2_fio2=450,
            evidence_ids=["Observation/resp-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.COAGULATION,
            platelets_10e9_l=200,
            evidence_ids=["Observation/plt-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.LIVER,
            bilirubin_mg_dl=0.8,
            evidence_ids=["Observation/bili-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.CARDIOVASCULAR,
            map_mmhg=80,
            evidence_ids=["Observation/map-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.CNS,
            gcs=15,
            evidence_ids=["Observation/gcs-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.RENAL,
            creatinine_mg_dl=0.9,
            evidence_ids=["Observation/cr-1"],
        ),
    ]


def test_complete_zero_score() -> None:
    result = compute_sofa_score(
        patient_id="Patient/t0-zero",
        event_time=T0,
        inputs=_full_mild(),
        rule_bundle_id="sepsis-sofa",
        rule_version="0.1.0",
    )
    assert result.completeness == ScoreCompleteness.COMPLETE
    assert result.total_score == 0
    assert result.missing_components == []
    assert tier_for_score(result.total_score) == AcuityTier.NONE


def test_complete_elevated_score_and_evidence() -> None:
    inputs = _full_mild()
    # platelets 40 → 3; bili 2.5 → 2; cr 2.1 → 2; total 7
    for i, inp in enumerate(inputs):
        if inp.name == SofaComponentName.COAGULATION:
            inputs[i] = inp.model_copy(update={"platelets_10e9_l": 40})
        if inp.name == SofaComponentName.LIVER:
            inputs[i] = inp.model_copy(update={"bilirubin_mg_dl": 2.5})
        if inp.name == SofaComponentName.RENAL:
            inputs[i] = inp.model_copy(update={"creatinine_mg_dl": 2.1})

    result = compute_sofa_score(
        patient_id="Patient/t0-high",
        event_time=T0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.1.0",
    )
    assert result.completeness == ScoreCompleteness.COMPLETE
    assert result.total_score == 7
    assert tier_for_score(result.total_score) == AcuityTier.CRITICAL
    assert "Observation/plt-1" in result.evidence_ids


def test_partial_missing_components_listed() -> None:
    inputs = [
        SofaComponentInput(
            name=SofaComponentName.COAGULATION,
            platelets_10e9_l=40,
            evidence_ids=["Observation/plt-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.LIVER,
            bilirubin_mg_dl=2.5,
            evidence_ids=["Observation/bili-1"],
        ),
        SofaComponentInput(
            name=SofaComponentName.RENAL,
            creatinine_mg_dl=2.1,
            evidence_ids=["Observation/cr-1"],
        ),
    ]
    result = compute_sofa_score(
        patient_id="Patient/t0-partial",
        event_time=T0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.1.0",
    )
    assert result.completeness == ScoreCompleteness.PARTIAL
    assert result.total_score == 7
    assert SofaComponentName.RESPIRATION in result.missing_components
    assert SofaComponentName.CNS in result.missing_components
    assert SofaComponentName.CARDIOVASCULAR in result.missing_components


def test_insufficient_data_when_too_few_components() -> None:
    inputs = [
        SofaComponentInput(
            name=SofaComponentName.COAGULATION,
            platelets_10e9_l=10,
            evidence_ids=["Observation/plt-1"],
        ),
    ]
    result = compute_sofa_score(
        patient_id="Patient/t0-insuff",
        event_time=T0,
        inputs=inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.1.0",
    )
    assert result.completeness == ScoreCompleteness.INSUFFICIENT_DATA
    assert result.total_score is None
    assert tier_for_score(result.total_score) == AcuityTier.NONE


@pytest.mark.parametrize(
    ("score", "tier"),
    [
        (None, AcuityTier.NONE),
        (0, AcuityTier.NONE),
        (1, AcuityTier.NONE),
        (2, AcuityTier.WATCH),
        (3, AcuityTier.WATCH),
        (4, AcuityTier.URGENT),
        (6, AcuityTier.URGENT),
        (7, AcuityTier.CRITICAL),
    ],
)
def test_tier_bands(score: int | None, tier: AcuityTier) -> None:
    assert tier_for_score(score) == tier
