"""T0 fixtures for AKI KDIGO-inspired scoring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eval.aki.scoring import (
    AkiInput,
    ScoreCompleteness,
    compute_aki_score,
    tier_for_aki_score,
)
from eval.sofa.scoring import AcuityTier

T0 = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)


def test_no_aki_when_stable() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-0",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=1.0,
            baseline_creatinine_mg_dl=1.0,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
    )
    assert result.completeness == ScoreCompleteness.COMPLETE
    assert result.stage == 0
    assert result.total_score == 0
    assert tier_for_aki_score(result.total_score) == AcuityTier.NONE


def test_stage1_delta() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-1",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=1.4,
            baseline_creatinine_mg_dl=1.0,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
    )
    assert result.stage == 1
    assert result.total_score == 2
    assert tier_for_aki_score(result.total_score) == AcuityTier.WATCH


def test_stage2_ratio() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-2",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=2.2,
            baseline_creatinine_mg_dl=1.0,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
    )
    assert result.stage == 2
    assert result.total_score == 4
    assert tier_for_aki_score(result.total_score) == AcuityTier.URGENT


def test_stage3_absolute() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-3",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=4.1,
            baseline_creatinine_mg_dl=1.2,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
    )
    assert result.stage == 3
    assert result.total_score == 6
    assert tier_for_aki_score(result.total_score) == AcuityTier.CRITICAL


def test_insufficient_without_creatinine() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-insuff",
        event_time=T0,
        inputs=AkiInput(baseline_creatinine_mg_dl=1.0),
    )
    assert result.completeness == ScoreCompleteness.INSUFFICIENT_DATA
    assert result.total_score is None


def test_partial_missing_baseline_non_absolute() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-partial",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=2.0,
            baseline_creatinine_mg_dl=None,
            evidence_ids=["Observation/cr-now"],
        ),
    )
    assert result.completeness == ScoreCompleteness.PARTIAL
    assert "baseline_creatinine" in result.missing_components
    assert result.stage == 0


def test_stage3_absolute_without_baseline() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-abs-no-base",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=4.2,
            baseline_creatinine_mg_dl=None,
            evidence_ids=["Observation/cr-now"],
        ),
    )
    assert result.completeness == ScoreCompleteness.PARTIAL
    assert result.stage == 3
    assert result.total_score == 6
    assert "baseline_creatinine" in result.missing_components


def test_stage1_borderline_delta_exactly_0_3() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-delta",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=1.3,
            baseline_creatinine_mg_dl=1.0,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
    )
    assert result.stage == 1
    assert result.total_score == 2


def test_urine_output_stage2_without_creatinine_rise() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-uo",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=1.0,
            baseline_creatinine_mg_dl=1.0,
            urine_ml_kg_h=0.4,
            urine_duration_hours=14,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
            urine_evidence_ids=["Observation/uo-1"],
        ),
    )
    assert result.creatinine_stage == 0
    assert result.urine_stage == 2
    assert result.stage == 2
    assert result.total_score == 4
    assert tier_for_aki_score(result.total_score) == AcuityTier.URGENT


def test_anuria_stage3() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-anuria",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=1.1,
            baseline_creatinine_mg_dl=1.0,
            anuria=True,
            urine_duration_hours=12,
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
            urine_evidence_ids=["Observation/uo-flag"],
        ),
    )
    assert result.urine_stage == 3
    assert result.stage == 3
    assert result.total_score == 6


def test_partial_urine_fields_listed_missing() -> None:
    result = compute_aki_score(
        patient_id="Patient/aki-t0-uo-partial",
        event_time=T0,
        inputs=AkiInput(
            creatinine_mg_dl=1.0,
            baseline_creatinine_mg_dl=1.0,
            urine_ml_kg_h=0.4,
            # duration missing
            evidence_ids=["Observation/cr-now"],
            baseline_evidence_ids=["Observation/cr-base"],
        ),
    )
    assert result.stage == 0
    assert "urine_output" in result.missing_components
    assert result.completeness == ScoreCompleteness.PARTIAL


@pytest.mark.parametrize(
    ("score", "tier"),
    [
        (None, AcuityTier.NONE),
        (0, AcuityTier.NONE),
        (2, AcuityTier.WATCH),
        (4, AcuityTier.URGENT),
        (6, AcuityTier.CRITICAL),
    ],
)
def test_aki_tier_bands(score: int | None, tier: AcuityTier) -> None:
    assert tier_for_aki_score(score) == tier
