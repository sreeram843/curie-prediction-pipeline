"""Hemodynamic shock / hyperlactatemia surveillance scorer (CURIE-036).

Prototype only — not clinically validated. Outputs are surveillance indicators,
not confirmed diagnoses of shock.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from eval.sofa.scoring import AcuityTier, ScoreCompleteness

_STAGE_TO_SCORE = {0: 0, 1: 2, 2: 4, 3: 6}


class HemoInputName(StrEnum):
    LACTATE = "lactate"
    MAP = "mean_arterial_pressure"
    VASOPRESSOR = "vasopressor"


class HemoInput(BaseModel):
    lactate_mmol_l: float | None = None
    map_mmhg: float | None = None
    on_vasopressor: bool | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class HemoComponentScore(BaseModel):
    name: str
    points: int | None = None
    missing: bool
    evidence_ids: list[str] = Field(default_factory=list)


class HemoScoreResult(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    patient_id: str
    encounter_id: str | None = None
    event_time: datetime
    stage: int | None = Field(default=None, ge=0, le=3)
    total_score: int | None = None
    completeness: ScoreCompleteness
    components: list[HemoComponentScore] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    criteria_met: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_bundle_id: str = "hemo-shock"
    rule_version: str = "0.1.0"
    signal_kind: str = "risk"
    # Explicit non-claim
    clinical_claim: str = "surveillance_indicator_not_diagnosis"


def _stage_lactate(v: float | None) -> tuple[int | None, list[str], list[str]]:
    if v is None:
        return None, [HemoInputName.LACTATE.value], []
    if v >= 4.0:
        return 3, [], ["lactate_ge_4"]
    if v >= 2.0:
        return 2, [], ["lactate_ge_2"]
    if v >= 1.5:
        return 1, [], ["lactate_ge_1_5"]
    return 0, [], ["lactate_ok"]


def _stage_map(v: float | None) -> tuple[int | None, list[str], list[str]]:
    if v is None:
        return None, [HemoInputName.MAP.value], []
    if v < 55:
        return 3, [], ["map_lt_55"]
    if v < 65:
        return 2, [], ["map_lt_65"]
    if v < 70:
        return 1, [], ["map_lt_70"]
    return 0, [], ["map_ok"]


def _stage_vaso(on: bool | None) -> tuple[int | None, list[str], list[str]]:
    if on is None:
        return None, [], []
    if on:
        return 2, [], ["on_vasopressor"]
    return 0, [], ["vaso_off"]


def compute_hemo_score(
    *,
    patient_id: str,
    event_time: datetime,
    inputs: HemoInput,
    rule_bundle_id: str = "hemo-shock",
    rule_version: str = "0.1.0",
    encounter_id: str | None = None,
) -> HemoScoreResult:
    lac_s, lac_m, lac_c = _stage_lactate(inputs.lactate_mmol_l)
    map_s, map_m, map_c = _stage_map(inputs.map_mmhg)
    vaso_s, vaso_m, vaso_c = _stage_vaso(inputs.on_vasopressor)
    stages = [s for s in (lac_s, map_s, vaso_s) if s is not None]
    missing = list(dict.fromkeys([*lac_m, *map_m, *vaso_m]))
    criteria = list(dict.fromkeys([*lac_c, *map_c, *vaso_c]))
    evidence = list(inputs.evidence_ids)

    if not stages:
        return HemoScoreResult(
            patient_id=patient_id,
            encounter_id=encounter_id,
            event_time=event_time,
            stage=None,
            total_score=None,
            completeness=ScoreCompleteness.INSUFFICIENT_DATA,
            missing_components=missing
            or [HemoInputName.LACTATE.value, HemoInputName.MAP.value],
            criteria_met=[],
            evidence_ids=evidence,
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
            components=[
                HemoComponentScore(name=HemoInputName.LACTATE.value, points=None, missing=True),
                HemoComponentScore(name=HemoInputName.MAP.value, points=None, missing=True),
            ],
        )

    stage = max(stages)
    score = _STAGE_TO_SCORE[stage]
    completeness = (
        ScoreCompleteness.PARTIAL if missing else ScoreCompleteness.COMPLETE
    )

    def _pts(s: int | None) -> int | None:
        return _STAGE_TO_SCORE[s] if s is not None else None

    return HemoScoreResult(
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_time=event_time,
        stage=stage,
        total_score=score,
        completeness=completeness,
        missing_components=missing,
        criteria_met=criteria,
        evidence_ids=evidence,
        rule_bundle_id=rule_bundle_id,
        rule_version=rule_version,
        components=[
            HemoComponentScore(
                name=HemoInputName.LACTATE.value,
                points=_pts(lac_s),
                missing=lac_s is None,
            ),
            HemoComponentScore(
                name=HemoInputName.MAP.value,
                points=_pts(map_s),
                missing=map_s is None,
            ),
            HemoComponentScore(
                name=HemoInputName.VASOPRESSOR.value,
                points=_pts(vaso_s),
                missing=False,
            ),
        ],
    )


def tier_for_hemo_score(score: int | None, *, naive_threshold: int = 2) -> AcuityTier:
    if score is None or score < naive_threshold:
        return AcuityTier.NONE
    if score >= 6:
        return AcuityTier.CRITICAL
    if score >= 4:
        return AcuityTier.URGENT
    return AcuityTier.WATCH
