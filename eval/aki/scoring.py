"""KDIGO-inspired AKI reference scorer (Phase 3 plugin).

Prototype only — not clinically validated. Missing values are never imputed.
v0.2: creatinine + urine-output staging; final stage = max of both.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from eval.sofa.scoring import AcuityTier, ScoreCompleteness


class AkiInputName(StrEnum):
    CREATININE = "creatinine"
    BASELINE_CREATININE = "baseline_creatinine"
    URINE_OUTPUT = "urine_output"


class AkiInput(BaseModel):
    creatinine_mg_dl: float | None = None
    baseline_creatinine_mg_dl: float | None = None
    # KDIGO UO path (requires weight-normalized rate + duration)
    urine_ml_kg_h: float | None = None
    urine_duration_hours: float | None = None
    anuria: bool | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    baseline_evidence_ids: list[str] = Field(default_factory=list)
    urine_evidence_ids: list[str] = Field(default_factory=list)


class AkiComponentScore(BaseModel):
    name: str
    points: int | None = None
    missing: bool
    evidence_ids: list[str] = Field(default_factory=list)


class AkiScoreResult(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    patient_id: str
    encounter_id: str | None = None
    event_time: datetime
    stage: int | None = Field(default=None, ge=0, le=3)
    creatinine_stage: int | None = Field(default=None, ge=0, le=3)
    urine_stage: int | None = Field(default=None, ge=0, le=3)
    total_score: int | None = Field(default=None, ge=0, le=24)
    completeness: ScoreCompleteness
    components: list[AkiComponentScore]
    missing_components: list[str]
    evidence_ids: list[str]
    rule_bundle_id: str
    rule_version: str


_STAGE_TO_SCORE = {0: 0, 1: 2, 2: 4, 3: 6}


def stage_from_creatinine(
    creatinine_mg_dl: float,
    baseline_creatinine_mg_dl: float | None,
) -> tuple[int, list[str]]:
    """Return (stage, missing_components)."""
    missing: list[str] = []
    if baseline_creatinine_mg_dl is None or baseline_creatinine_mg_dl <= 0:
        missing.append(AkiInputName.BASELINE_CREATININE.value)
        # Absolute escape hatch only
        if creatinine_mg_dl >= 4.0:
            return 3, missing
        return 0, missing

    ratio = creatinine_mg_dl / baseline_creatinine_mg_dl
    delta = creatinine_mg_dl - baseline_creatinine_mg_dl
    if ratio >= 3.0 or creatinine_mg_dl >= 4.0:
        return 3, missing
    if ratio >= 2.0:
        return 2, missing
    if ratio >= 1.5 or delta >= 0.3:
        return 1, missing
    return 0, missing


def stage_from_urine(
    *,
    urine_ml_kg_h: float | None,
    urine_duration_hours: float | None,
    anuria: bool | None,
) -> tuple[int | None, list[str]]:
    """KDIGO-inspired UO staging. Returns (stage|None, missing).

    None stage means UO path not evaluable (inputs absent) — not a missing-error
    unless the caller expected UO; we only list missing when partial UO fields given.
    """
    missing: list[str] = []
    if anuria is True and (urine_duration_hours or 0) >= 12:
        return 3, missing

    if urine_ml_kg_h is None and urine_duration_hours is None and not anuria:
        return None, missing

    if urine_ml_kg_h is None or urine_duration_hours is None:
        missing.append(AkiInputName.URINE_OUTPUT.value)
        return None, missing

    rate = urine_ml_kg_h
    hours = urine_duration_hours
    if rate < 0.3 and hours >= 24:
        return 3, missing
    if rate < 0.5 and hours >= 12:
        return 2, missing
    if rate < 0.5 and hours >= 6:
        return 1, missing
    return 0, missing


def compute_aki_score(
    *,
    patient_id: str,
    event_time: datetime,
    inputs: AkiInput,
    rule_bundle_id: str = "aki-kdigo",
    rule_version: str = "0.2.0",
    encounter_id: str | None = None,
) -> AkiScoreResult:
    evidence = list(
        dict.fromkeys(
            [
                *inputs.evidence_ids,
                *inputs.baseline_evidence_ids,
                *inputs.urine_evidence_ids,
            ]
        )
    )

    has_cr = inputs.creatinine_mg_dl is not None
    uo_stage, uo_missing = stage_from_urine(
        urine_ml_kg_h=inputs.urine_ml_kg_h,
        urine_duration_hours=inputs.urine_duration_hours,
        anuria=inputs.anuria,
    )

    if not has_cr and uo_stage is None:
        missing = [AkiInputName.CREATININE.value, *uo_missing]
        # Dedup
        missing = list(dict.fromkeys(missing))
        return AkiScoreResult(
            patient_id=patient_id,
            encounter_id=encounter_id,
            event_time=event_time,
            stage=None,
            creatinine_stage=None,
            urine_stage=None,
            total_score=None,
            completeness=ScoreCompleteness.INSUFFICIENT_DATA,
            components=[
                AkiComponentScore(
                    name=AkiInputName.CREATININE.value,
                    points=None,
                    missing=True,
                )
            ],
            missing_components=missing or [AkiInputName.CREATININE.value],
            evidence_ids=evidence,
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
        )

    cr_stage: int | None = None
    cr_missing: list[str] = []
    if has_cr:
        assert inputs.creatinine_mg_dl is not None
        cr_stage, cr_missing = stage_from_creatinine(
            inputs.creatinine_mg_dl, inputs.baseline_creatinine_mg_dl
        )

    stages = [s for s in (cr_stage, uo_stage) if s is not None]
    stage = max(stages) if stages else 0
    score = _STAGE_TO_SCORE[stage]
    missing = list(dict.fromkeys([*cr_missing, *uo_missing]))
    completeness = (
        ScoreCompleteness.PARTIAL if missing else ScoreCompleteness.COMPLETE
    )

    components = [
        AkiComponentScore(
            name=AkiInputName.CREATININE.value,
            points=_STAGE_TO_SCORE[cr_stage] if cr_stage is not None else None,
            missing=not has_cr,
            evidence_ids=list(inputs.evidence_ids),
        ),
        AkiComponentScore(
            name=AkiInputName.BASELINE_CREATININE.value,
            points=None if AkiInputName.BASELINE_CREATININE.value in missing else 0,
            missing=AkiInputName.BASELINE_CREATININE.value in missing,
            evidence_ids=list(inputs.baseline_evidence_ids),
        ),
        AkiComponentScore(
            name=AkiInputName.URINE_OUTPUT.value,
            points=_STAGE_TO_SCORE[uo_stage] if uo_stage is not None else None,
            missing=AkiInputName.URINE_OUTPUT.value in missing,
            evidence_ids=list(inputs.urine_evidence_ids),
        ),
    ]
    return AkiScoreResult(
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_time=event_time,
        stage=stage,
        creatinine_stage=cr_stage,
        urine_stage=uo_stage,
        total_score=score,
        completeness=completeness,
        components=components,
        missing_components=missing,
        evidence_ids=evidence,
        rule_bundle_id=rule_bundle_id,
        rule_version=rule_version,
    )


def tier_for_aki_score(score: int | None, *, naive_threshold: int = 2) -> AcuityTier:
    if score is None or score < naive_threshold:
        return AcuityTier.NONE
    if score >= 6:
        return AcuityTier.CRITICAL
    if score >= 4:
        return AcuityTier.URGENT
    return AcuityTier.WATCH
