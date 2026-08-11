"""KDIGO-inspired AKI reference scorer (Phase 3 plugin).

Prototype only — not clinically validated. Missing values are never imputed.
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


class AkiInput(BaseModel):
    creatinine_mg_dl: float | None = None
    baseline_creatinine_mg_dl: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    baseline_evidence_ids: list[str] = Field(default_factory=list)


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


def compute_aki_score(
    *,
    patient_id: str,
    event_time: datetime,
    inputs: AkiInput,
    rule_bundle_id: str = "aki-kdigo",
    rule_version: str = "0.1.0",
    encounter_id: str | None = None,
) -> AkiScoreResult:
    evidence = list(dict.fromkeys([*inputs.evidence_ids, *inputs.baseline_evidence_ids]))

    if inputs.creatinine_mg_dl is None:
        return AkiScoreResult(
            patient_id=patient_id,
            encounter_id=encounter_id,
            event_time=event_time,
            stage=None,
            total_score=None,
            completeness=ScoreCompleteness.INSUFFICIENT_DATA,
            components=[
                AkiComponentScore(
                    name=AkiInputName.CREATININE.value,
                    points=None,
                    missing=True,
                )
            ],
            missing_components=[AkiInputName.CREATININE.value],
            evidence_ids=evidence,
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
        )

    stage, missing = stage_from_creatinine(
        inputs.creatinine_mg_dl, inputs.baseline_creatinine_mg_dl
    )
    score = _STAGE_TO_SCORE[stage]
    completeness = (
        ScoreCompleteness.PARTIAL if missing else ScoreCompleteness.COMPLETE
    )
    components = [
        AkiComponentScore(
            name=AkiInputName.CREATININE.value,
            points=score,
            missing=False,
            evidence_ids=list(inputs.evidence_ids),
        ),
        AkiComponentScore(
            name=AkiInputName.BASELINE_CREATININE.value,
            points=None if AkiInputName.BASELINE_CREATININE.value in missing else 0,
            missing=AkiInputName.BASELINE_CREATININE.value in missing,
            evidence_ids=list(inputs.baseline_evidence_ids),
        ),
    ]
    return AkiScoreResult(
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_time=event_time,
        stage=stage,
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
