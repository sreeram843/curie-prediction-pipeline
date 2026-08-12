"""Deterministic hypoxemic / ventilatory deterioration scorer (CURIE-013).

Prototype only — not clinically validated. Missing values are never imputed.
SpO2 alone does not assume ambient FiO2 unless ``room_air`` is explicitly true.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from eval.sofa.scoring import AcuityTier, ScoreCompleteness


class RespInputName(StrEnum):
    OXYGENATION = "oxygenation"
    RESPIRATORY_RATE = "respiratory_rate"
    OXYGEN_SUPPORT = "oxygen_support"
    BLOOD_GAS = "blood_gas"


class OxygenDevice(StrEnum):
    NONE = "none"
    NASAL_CANNULA = "nasal_cannula"
    FACE_MASK = "face_mask"
    HIGH_FLOW = "high_flow"
    NON_INVASIVE = "non_invasive"
    INVASIVE = "invasive"


_DEVICE_STAGE: dict[str, int] = {
    OxygenDevice.NONE.value: 0,
    OxygenDevice.NASAL_CANNULA.value: 1,
    OxygenDevice.FACE_MASK.value: 1,
    OxygenDevice.HIGH_FLOW.value: 2,
    OxygenDevice.NON_INVASIVE.value: 2,
    OxygenDevice.INVASIVE.value: 3,
}

_STAGE_TO_SCORE = {0: 0, 1: 2, 2: 4, 3: 6}


class RespInput(BaseModel):
    spo2_percent: float | None = None
    pao2_mmhg: float | None = None
    fio2_fraction: float | None = None
    pao2_fio2: float | None = None
    spo2_fio2: float | None = None
    room_air: bool | None = None
    respiratory_rate: float | None = None
    oxygen_device: str | None = None
    mechanically_ventilated: bool | None = None
    # Blood-gas context (optional; never imputed)
    abg_ph: float | None = None
    paco2_mmhg: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    oxygenation_evidence_ids: list[str] = Field(default_factory=list)
    rate_evidence_ids: list[str] = Field(default_factory=list)
    support_evidence_ids: list[str] = Field(default_factory=list)
    gas_evidence_ids: list[str] = Field(default_factory=list)


class RespComponentScore(BaseModel):
    name: str
    points: int | None = None
    missing: bool
    evidence_ids: list[str] = Field(default_factory=list)


class RespScoreResult(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    patient_id: str
    encounter_id: str | None = None
    event_time: datetime
    stage: int | None = Field(default=None, ge=0, le=3)
    oxygenation_stage: int | None = Field(default=None, ge=0, le=3)
    rate_stage: int | None = Field(default=None, ge=0, le=3)
    support_stage: int | None = Field(default=None, ge=0, le=3)
    blood_gas_stage: int | None = Field(default=None, ge=0, le=3)
    total_score: int | None = Field(default=None, ge=0, le=24)
    completeness: ScoreCompleteness
    components: list[RespComponentScore]
    missing_components: list[str]
    criteria_met: list[str] = Field(default_factory=list)
    evidence_ids: list[str]
    rule_bundle_id: str
    rule_version: str
    ratio_used: float | None = None
    ratio_source: str | None = None


def effective_resp_ratio(inp: RespInput) -> tuple[float | None, str | None]:
    """Return (ratio, source). PaO2/FiO2 preferred over SpO2/FiO2."""
    if inp.pao2_fio2 is not None:
        return inp.pao2_fio2, "pao2_fio2"
    if inp.spo2_fio2 is not None:
        return inp.spo2_fio2, "spo2_fio2"

    fio2 = inp.fio2_fraction
    if fio2 is None and inp.room_air is True:
        fio2 = 0.21
    if fio2 is None or fio2 <= 0:
        return None, None

    if inp.pao2_mmhg is not None:
        return inp.pao2_mmhg / fio2, "pao2_mmhg/fio2"
    if inp.spo2_percent is not None:
        return inp.spo2_percent / fio2, "spo2_percent/fio2"
    return None, None


def stage_from_oxygenation(inp: RespInput) -> tuple[int | None, list[str], list[str]]:
    """(stage|None, missing, criteria_met)."""
    missing: list[str] = []
    criteria: list[str] = []
    ratio, source = effective_resp_ratio(inp)
    if ratio is None:
        # Partial SpO2 without FiO2 is not evaluable (no ambient assumption)
        if inp.spo2_percent is not None or inp.pao2_mmhg is not None:
            missing.append(RespInputName.OXYGENATION.value)
        return None, missing, criteria

    if ratio < 100:
        criteria.append(f"ratio_lt_100:{source}")
        return 3, missing, criteria
    if ratio < 200:
        criteria.append(f"ratio_lt_200:{source}")
        return 3 if inp.mechanically_ventilated else 2, missing, criteria
    if ratio < 300:
        criteria.append(f"ratio_lt_300:{source}")
        return 2, missing, criteria
    if ratio < 400:
        criteria.append(f"ratio_lt_400:{source}")
        return 1, missing, criteria
    criteria.append(f"ratio_ok:{source}")
    return 0, missing, criteria


def stage_from_rate(rr: float | None) -> tuple[int | None, list[str], list[str]]:
    if rr is None:
        return None, [], []
    if rr >= 35:
        return 3, [], ["rr_ge_35"]
    if rr >= 30:
        return 2, [], ["rr_ge_30"]
    if rr >= 22:
        return 1, [], ["rr_ge_22"]
    return 0, [], ["rr_ok"]


def stage_from_support(
    *,
    oxygen_device: str | None,
    mechanically_ventilated: bool | None,
) -> tuple[int | None, list[str], list[str]]:
    criteria: list[str] = []
    if mechanically_ventilated is True:
        criteria.append("mechanically_ventilated")
        return 3, [], criteria
    if oxygen_device is None:
        return None, [], criteria
    device = oxygen_device.strip().lower()
    stage = _DEVICE_STAGE.get(device)
    if stage is None:
        return None, [RespInputName.OXYGEN_SUPPORT.value], criteria
    if stage > 0:
        criteria.append(f"oxygen_device:{device}")
    return stage, [], criteria


def stage_from_blood_gas(
    *,
    abg_ph: float | None,
    paco2_mmhg: float | None,
) -> tuple[int | None, list[str], list[str]]:
    """Optional ABG context. Absent entirely → not evaluable (not missing-error)."""
    if abg_ph is None and paco2_mmhg is None:
        return None, [], []
    criteria: list[str] = []
    stage = 0
    if abg_ph is not None:
        if abg_ph < 7.20:
            stage = max(stage, 3)
            criteria.append("ph_lt_7_20")
        elif abg_ph < 7.25:
            stage = max(stage, 2)
            criteria.append("ph_lt_7_25")
        elif abg_ph < 7.30:
            stage = max(stage, 1)
            criteria.append("ph_lt_7_30")
    if paco2_mmhg is not None:
        if paco2_mmhg > 60:
            stage = max(stage, 2)
            criteria.append("paco2_gt_60")
        elif paco2_mmhg > 50:
            stage = max(stage, 1)
            criteria.append("paco2_gt_50")
    if not criteria:
        criteria.append("abg_ok")
    return stage, [], criteria


def compute_resp_score(
    *,
    patient_id: str,
    event_time: datetime,
    inputs: RespInput,
    rule_bundle_id: str = "resp-deterioration",
    rule_version: str = "0.1.0",
    encounter_id: str | None = None,
) -> RespScoreResult:
    evidence = list(
        dict.fromkeys(
            [
                *inputs.evidence_ids,
                *inputs.oxygenation_evidence_ids,
                *inputs.rate_evidence_ids,
                *inputs.support_evidence_ids,
                *inputs.gas_evidence_ids,
            ]
        )
    )
    ratio, ratio_source = effective_resp_ratio(inputs)

    ox_stage, ox_missing, ox_crit = stage_from_oxygenation(inputs)
    rr_stage, rr_missing, rr_crit = stage_from_rate(inputs.respiratory_rate)
    sup_stage, sup_missing, sup_crit = stage_from_support(
        oxygen_device=inputs.oxygen_device,
        mechanically_ventilated=inputs.mechanically_ventilated,
    )
    gas_stage, gas_missing, gas_crit = stage_from_blood_gas(
        abg_ph=inputs.abg_ph,
        paco2_mmhg=inputs.paco2_mmhg,
    )

    stages = [s for s in (ox_stage, rr_stage, sup_stage, gas_stage) if s is not None]
    missing = list(
        dict.fromkeys([*ox_missing, *rr_missing, *sup_missing, *gas_missing])
    )
    criteria = list(dict.fromkeys([*ox_crit, *rr_crit, *sup_crit, *gas_crit]))

    if not stages:
        return RespScoreResult(
            patient_id=patient_id,
            encounter_id=encounter_id,
            event_time=event_time,
            stage=None,
            total_score=None,
            completeness=ScoreCompleteness.INSUFFICIENT_DATA,
            components=[
                RespComponentScore(
                    name=RespInputName.OXYGENATION.value,
                    points=None,
                    missing=True,
                )
            ],
            missing_components=missing
            or [
                RespInputName.OXYGENATION.value,
                RespInputName.RESPIRATORY_RATE.value,
                RespInputName.OXYGEN_SUPPORT.value,
            ],
            criteria_met=[],
            evidence_ids=evidence,
            rule_bundle_id=rule_bundle_id,
            rule_version=rule_version,
            ratio_used=ratio,
            ratio_source=ratio_source,
        )

    stage = max(stages)
    score = _STAGE_TO_SCORE[stage]
    completeness = (
        ScoreCompleteness.PARTIAL if missing else ScoreCompleteness.COMPLETE
    )

    def _pts(s: int | None) -> int | None:
        return _STAGE_TO_SCORE[s] if s is not None else None

    components = [
        RespComponentScore(
            name=RespInputName.OXYGENATION.value,
            points=_pts(ox_stage),
            missing=ox_stage is None
            and RespInputName.OXYGENATION.value in missing,
            evidence_ids=list(inputs.oxygenation_evidence_ids),
        ),
        RespComponentScore(
            name=RespInputName.RESPIRATORY_RATE.value,
            points=_pts(rr_stage),
            missing=False,
            evidence_ids=list(inputs.rate_evidence_ids),
        ),
        RespComponentScore(
            name=RespInputName.OXYGEN_SUPPORT.value,
            points=_pts(sup_stage),
            missing=RespInputName.OXYGEN_SUPPORT.value in missing,
            evidence_ids=list(inputs.support_evidence_ids),
        ),
        RespComponentScore(
            name=RespInputName.BLOOD_GAS.value,
            points=_pts(gas_stage),
            missing=False,
            evidence_ids=list(inputs.gas_evidence_ids),
        ),
    ]
    return RespScoreResult(
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_time=event_time,
        stage=stage,
        oxygenation_stage=ox_stage,
        rate_stage=rr_stage,
        support_stage=sup_stage,
        blood_gas_stage=gas_stage,
        total_score=score,
        completeness=completeness,
        components=components,
        missing_components=missing,
        criteria_met=criteria,
        evidence_ids=evidence,
        rule_bundle_id=rule_bundle_id,
        rule_version=rule_version,
        ratio_used=ratio,
        ratio_source=ratio_source,
    )


def tier_for_resp_score(score: int | None, *, naive_threshold: int = 2) -> AcuityTier:
    if score is None or score < naive_threshold:
        return AcuityTier.NONE
    if score >= 6:
        return AcuityTier.CRITICAL
    if score >= 4:
        return AcuityTier.URGENT
    return AcuityTier.WATCH
