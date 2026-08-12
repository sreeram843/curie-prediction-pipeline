"""SOFA-style sepsis score models and deterministic component scoring (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from eval.sofa.thresholds import SofaThresholds


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
    # Respiration — prefer explicit ratios; else raw SpO2/PaO2 only with FiO2 (no ambient proxy)
    pao2_fio2: float | None = None
    spo2_fio2: float | None = None
    spo2_percent: float | None = None
    pao2_mmhg: float | None = None
    fio2_fraction: float | None = None
    mechanically_ventilated: bool | None = None
    # Coagulation
    platelets_10e9_l: float | None = None
    # Liver
    bilirubin_mg_dl: float | None = None
    # Cardiovascular
    map_mmhg: float | None = None
    on_vasopressors: bool | None = None
    # Vincent SOFA pressor ladder (ug/kg/min). Agent optional when only boolean known.
    vasopressor_agent: (
        Literal["dopamine", "dobutamine", "epinephrine", "norepinephrine", "other"] | None
    ) = None
    vasopressor_dose_ug_kg_min: float | None = None
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
    indicator: str = "sofa-deterioration"
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


def effective_resp_ratio(inp: SofaComponentInput) -> float | None:
    """Prefer explicit ratios; else PaO2/FiO2 or SpO2/FiO2 when FiO2 known. Never assumes 0.21."""
    if inp.pao2_fio2 is not None:
        return inp.pao2_fio2
    if inp.spo2_fio2 is not None:
        return inp.spo2_fio2
    if inp.fio2_fraction is None or inp.fio2_fraction <= 0:
        return None
    if inp.pao2_mmhg is not None:
        return inp.pao2_mmhg / inp.fio2_fraction
    if inp.spo2_percent is not None:
        return inp.spo2_percent / inp.fio2_fraction
    return None


def score_respiration(
    inp: SofaComponentInput, thresholds: SofaThresholds | None = None
) -> int | None:
    th = thresholds or SofaThresholds.defaults()
    ratio = effective_resp_ratio(inp)
    if ratio is None:
        return None
    vent = bool(inp.mechanically_ventilated)
    if ratio < th.resp_p4_lt and vent:
        return 4
    if ratio < th.resp_p3_lt and vent:
        return 3
    if ratio < th.resp_p2_lt:
        return 2
    if ratio < th.resp_p1_lt:
        return 1
    return 0


def score_coagulation(
    inp: SofaComponentInput, thresholds: SofaThresholds | None = None
) -> int | None:
    th = thresholds or SofaThresholds.defaults()
    p = inp.platelets_10e9_l
    if p is None:
        return None
    for band in th.coag:
        if band.max_exclusive is not None and p < band.max_exclusive:
            return band.points
        if band.min_inclusive is not None and p >= band.min_inclusive:
            return band.points
    return 0


def score_liver(inp: SofaComponentInput, thresholds: SofaThresholds | None = None) -> int | None:
    th = thresholds or SofaThresholds.defaults()
    b = inp.bilirubin_mg_dl
    if b is None:
        return None
    for band in th.liver:
        if band.min_inclusive is not None and b >= band.min_inclusive:
            return band.points
        if band.max_exclusive is not None and b < band.max_exclusive:
            return band.points
    return 0


def score_cardiovascular(
    inp: SofaComponentInput, thresholds: SofaThresholds | None = None
) -> int | None:
    th = thresholds or SofaThresholds.defaults()
    pressor = _vasopressor_points(inp, th)
    if pressor is not None:
        return pressor
    if inp.map_mmhg is None and inp.on_vasopressors is None:
        return None
    if inp.map_mmhg is not None and inp.map_mmhg < th.map_lt:
        return th.map_points
    if inp.map_mmhg is not None:
        return 0
    return None


def _vasopressor_points(inp: SofaComponentInput, th: SofaThresholds) -> int | None:
    agent = (inp.vasopressor_agent or "").lower() or None
    dose = inp.vasopressor_dose_ug_kg_min
    if agent == "dobutamine":
        return 2
    if agent == "dopamine" and dose is not None:
        if dose > th.dopamine_p3_max:
            return 4
        if dose > th.dopamine_p2_max:
            return 3
        return 2
    if agent in {"epinephrine", "norepinephrine"} and dose is not None:
        if dose > th.epi_norepi_p3_max:
            return 4
        return 3
    if agent == "other" and dose is not None:
        return 3 if dose <= th.epi_norepi_p3_max else 4
    if inp.on_vasopressors is True or agent is not None:
        return th.unknown_pressor_points
    return None


def score_cns(inp: SofaComponentInput, thresholds: SofaThresholds | None = None) -> int | None:
    th = thresholds or SofaThresholds.defaults()
    g = inp.gcs
    if g is None:
        return None
    for band in th.cns:
        if band.gcs_lt is not None and g < band.gcs_lt:
            return band.points
        if band.gcs_le is not None and g <= band.gcs_le:
            return band.points
        if band.gcs_eq is not None and g == band.gcs_eq:
            return band.points
    return 0


def score_renal(inp: SofaComponentInput, thresholds: SofaThresholds | None = None) -> int | None:
    th = thresholds or SofaThresholds.defaults()
    points: list[int] = []
    c = inp.creatinine_mg_dl
    if c is not None:
        for band in th.renal_cr:
            if band.min_inclusive is not None and c >= band.min_inclusive:
                points.append(band.points)
                break
            if band.max_exclusive is not None and c < band.max_exclusive:
                points.append(band.points)
                break
    u = inp.urine_output_ml_day
    if u is not None:
        for band in th.renal_uo:
            if band.max_exclusive is not None and u < band.max_exclusive:
                points.append(band.points)
                break
            if band.min_inclusive is not None and u >= band.min_inclusive:
                points.append(band.points)
                break
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
    thresholds: SofaThresholds | None = None,
    rule_bundle: dict | None = None,
) -> SofaScoreResult:
    th = thresholds
    if th is None and rule_bundle is not None:
        th = SofaThresholds.from_bundle(rule_bundle)
    if th is None:
        th = SofaThresholds.defaults()

    by_name = {i.name: i for i in inputs}
    components: list[SofaComponentScore] = []
    evidence: list[str] = []

    for name in SOFA_COMPONENTS:
        inp = by_name.get(name) or SofaComponentInput(name=name)
        points = _SCORERS[name](inp, th)
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


def tier_for_score(
    score: int | None,
    *,
    naive_threshold: int = 2,
    severity_bands: list[dict] | None = None,
) -> AcuityTier:
    if score is None or score < naive_threshold:
        return AcuityTier.NONE
    if severity_bands:
        for band in severity_bands:
            if int(band["min"]) <= score <= int(band["max"]):
                return AcuityTier(str(band["tier"]))
        last = severity_bands[-1]
        if score > int(last["max"]):
            return AcuityTier(str(last["tier"]))
        return AcuityTier.NONE
    if score >= 7:
        return AcuityTier.CRITICAL
    if score >= 4:
        return AcuityTier.URGENT
    return AcuityTier.WATCH
