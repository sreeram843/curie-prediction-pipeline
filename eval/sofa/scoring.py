"""SOFA-style sepsis score models and deterministic component scoring (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SofaComponentName(StrEnum):
    RESPIRATION = "respiration"
    COAGULATION = "coagulation"
    LIVER = "liver"
    CARDIOVASCULAR = "cardiovascular"
    CNS = "cns"
    RENAL = "renal"


SOFA_COMPONENTS: tuple[SofaComponentName, ...] = tuple(SofaComponentName)


class ScoreCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT_DATA = "insufficient_data"


class AcuityTier(StrEnum):
    NONE = "none"
    WATCH = "watch"
    URGENT = "urgent"
    CRITICAL = "critical"


class SofaComponentInput(BaseModel):
    """Raw clinical values available for one SOFA component at score time."""

    name: SofaComponentName
    # Respiration
    pao2_fio2: float | None = None
    spo2_fio2: float | None = None
    mechanically_ventilated: bool | None = None
    # Coagulation
    platelets_10e9_l: float | None = None
    # Liver
    bilirubin_mg_dl: float | None = None
    # Cardiovascular
    map_mmhg: float | None = None
    on_vasopressors: bool | None = None
    # CNS
    gcs: int | None = Field(default=None, ge=3, le=15)
    # Renal
    creatinine_mg_dl: float | None = None
    urine_output_ml_day: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class SofaComponentScore(BaseModel):
    name: SofaComponentName
    points: int | None = Field(default=None, ge=0, le=4)
    missing: bool
    evidence_ids: list[str] = Field(default_factory=list)


class SofaScoreResult(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    patient_id: str
    encounter_id: str | None = None
    event_time: datetime
    total_score: int | None = Field(default=None, ge=0, le=24)
    completeness: ScoreCompleteness
    components: list[SofaComponentScore]
    missing_components: list[SofaComponentName]
    evidence_ids: list[str]
    rule_bundle_id: str
    rule_version: str
    min_components_required: int = 3

    @model_validator(mode="after")
    def _consistency(self) -> SofaScoreResult:
        missing = [c.name for c in self.components if c.missing]
        if list(self.missing_components) != missing:
            object.__setattr__(self, "missing_components", missing)
        return self


class AlertEvent(BaseModel):
    """Internal alert event emitted to the `alerts` topic (pre-FHIR RiskAssessment)."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    alert_id: str
    patient_id: str
    encounter_id: str | None = None
    indicator: Literal["sepsis"] = "sepsis"
    event_time: datetime
    ingest_time: datetime
    score: int | None
    completeness: ScoreCompleteness
    tier: AcuityTier
    component_breakdown: list[SofaComponentScore]
    missing_components: list[SofaComponentName]
    evidence_ids: list[str]
    rule_bundle_id: str
    rule_version: str
    governance_path: Literal["naive", "governed"] = "naive"
    suppressed: bool = False
    suppression_reason: str | None = None


def score_respiration(inp: SofaComponentInput) -> int | None:
    ratio = inp.pao2_fio2 if inp.pao2_fio2 is not None else inp.spo2_fio2
    if ratio is None:
        return None
    vent = bool(inp.mechanically_ventilated)
    if ratio < 100 and vent:
        return 4
    if ratio < 200 and vent:
        return 3
    if ratio < 300:
        return 2
    if ratio < 400:
        return 1
    return 0


def score_coagulation(inp: SofaComponentInput) -> int | None:
    p = inp.platelets_10e9_l
    if p is None:
        return None
    if p < 20:
        return 4
    if p < 50:
        return 3
    if p < 100:
        return 2
    if p < 150:
        return 1
    return 0


def score_liver(inp: SofaComponentInput) -> int | None:
    b = inp.bilirubin_mg_dl
    if b is None:
        return None
    if b >= 12.0:
        return 4
    if b >= 6.0:
        return 3
    if b >= 2.0:
        return 2
    if b >= 1.2:
        return 1
    return 0


def score_cardiovascular(inp: SofaComponentInput) -> int | None:
    if inp.on_vasopressors is True:
        # Prototype simplification: any vasopressor → at least 3 (full dose ladder later)
        return 3
    if inp.map_mmhg is None and inp.on_vasopressors is None:
        return None
    if inp.map_mmhg is not None and inp.map_mmhg < 70:
        return 1
    if inp.map_mmhg is not None:
        return 0
    return None


def score_cns(inp: SofaComponentInput) -> int | None:
    g = inp.gcs
    if g is None:
        return None
    if g < 6:
        return 4
    if g <= 9:
        return 3
    if g <= 12:
        return 2
    if g <= 14:
        return 1
    return 0


def score_renal(inp: SofaComponentInput) -> int | None:
    c = inp.creatinine_mg_dl
    u = inp.urine_output_ml_day
    points: list[int] = []
    if c is not None:
        if c >= 5.0:
            points.append(4)
        elif c >= 3.5:
            points.append(3)
        elif c >= 2.0:
            points.append(2)
        elif c >= 1.2:
            points.append(1)
        else:
            points.append(0)
    if u is not None:
        if u < 200:
            points.append(4)
        elif u < 500:
            points.append(3)
        else:
            points.append(0)
    if not points:
        return None
    return max(points)


_SCORERS = {
    SofaComponentName.RESPIRATION: score_respiration,
    SofaComponentName.COAGULATION: score_coagulation,
    SofaComponentName.LIVER: score_liver,
    SofaComponentName.CARDIOVASCULAR: score_cardiovascular,
    SofaComponentName.CNS: score_cns,
    SofaComponentName.RENAL: score_renal,
}


def compute_sofa_score(
    *,
    patient_id: str,
    event_time: datetime,
    inputs: list[SofaComponentInput],
    rule_bundle_id: str,
    rule_version: str,
    encounter_id: str | None = None,
    min_components_required: int = 3,
) -> SofaScoreResult:
    by_name = {i.name: i for i in inputs}
    components: list[SofaComponentScore] = []
    evidence: list[str] = []

    for name in SOFA_COMPONENTS:
        inp = by_name.get(name) or SofaComponentInput(name=name)
        points = _SCORERS[name](inp)
        missing = points is None
        components.append(
            SofaComponentScore(
                name=name,
                points=points,
                missing=missing,
                evidence_ids=list(inp.evidence_ids),
            )
        )
        evidence.extend(inp.evidence_ids)

    present = [c for c in components if not c.missing]
    missing_names = [c.name for c in components if c.missing]

    if len(present) < min_components_required:
        completeness = ScoreCompleteness.INSUFFICIENT_DATA
        total = None
    elif missing_names:
        completeness = ScoreCompleteness.PARTIAL
        total = sum(c.points or 0 for c in present)
    else:
        completeness = ScoreCompleteness.COMPLETE
        total = sum(c.points or 0 for c in present)

    # Dedup evidence while preserving order
    seen: set[str] = set()
    uniq_evidence: list[str] = []
    for e in evidence:
        if e not in seen:
            seen.add(e)
            uniq_evidence.append(e)

    return SofaScoreResult(
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_time=event_time,
        total_score=total,
        completeness=completeness,
        components=components,
        missing_components=missing_names,
        evidence_ids=uniq_evidence,
        rule_bundle_id=rule_bundle_id,
        rule_version=rule_version,
        min_components_required=min_components_required,
    )


def tier_for_score(score: int | None, *, naive_threshold: int = 2) -> AcuityTier:
    if score is None or score < naive_threshold:
        return AcuityTier.NONE
    if score >= 7:
        return AcuityTier.CRITICAL
    if score >= 4:
        return AcuityTier.URGENT
    return AcuityTier.WATCH
