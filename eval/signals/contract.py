"""Common clinical-signal output contract (CURIE-010).

Prototype only — not clinically validated.

Every indicator (SOFA deterioration, AKI, sepsis-3 phenotype, and future
signals) projects onto this top-level schema before API/dashboard rendering.
Condition-specific detail may live under ``extensions``; UIs must not require
it to render an unknown ``signal_type``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

SIGNAL_CONTRACT_VERSION = "1.0.0"


class SignalKind(StrEnum):
    """Phenotype vs continuous risk / deterioration score."""

    RISK = "risk"
    PHENOTYPE = "phenotype"


class ResolutionState(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class SignalComponent(BaseModel):
    name: str
    points: int | None = None
    missing: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class ClinicalSignal(BaseModel):
    """Shared top-level clinical signal (SOFA, AKI, sepsis-3, …)."""

    schema_version: Literal["1.0.0"] = SIGNAL_CONTRACT_VERSION
    signal_id: str
    signal_type: str
    signal_kind: SignalKind
    patient_id: str
    encounter_id: str | None = None
    event_time: datetime
    score: int | None = None
    stage: int | None = None
    completeness: str = "partial"
    severity: str = "none"
    onset_time: datetime | None = None
    required_inputs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    criteria_met: list[str] = Field(default_factory=list)
    rule_bundle_id: str
    rule_version: str
    rule_bundle_hash: str | None = None
    resolution_state: ResolutionState = ResolutionState.OPEN
    components: list[SignalComponent] = Field(default_factory=list)
    # Indicator-specific extras (never required for generic rendering)
    extensions: dict[str, Any] = Field(default_factory=dict)

    def to_alert_fields(self) -> dict[str, Any]:
        """Map contract fields onto the legacy AlertRecord / Kafka alert shape."""
        return {
            "alert_id": self.signal_id,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "indicator": self.signal_type,
            "signal_kind": self.signal_kind.value,
            "event_time": self.event_time,
            "score": self.score,
            "stage": self.stage,
            "completeness": self.completeness,
            "tier": self.severity,
            "onset_time": self.onset_time,
            "required_inputs": list(self.required_inputs),
            "missing_components": list(self.missing_inputs),
            "evidence_ids": list(self.evidence_ids),
            "exclusions": list(self.exclusions),
            "criteria_met": list(self.criteria_met),
            "rule_bundle_id": self.rule_bundle_id,
            "rule_version": self.rule_version,
            "rule_bundle_hash": self.rule_bundle_hash,
            "resolution_state": self.resolution_state.value,
            "component_breakdown": [
                {
                    "name": c.name,
                    "points": c.points,
                    "missing": c.missing,
                    "evidence_ids": list(c.evidence_ids),
                }
                for c in self.components
            ],
            "signal": self.model_dump(mode="json"),
        }


def _components_from_breakdown(items: list[Any]) -> list[SignalComponent]:
    out: list[SignalComponent] = []
    for item in items:
        if isinstance(item, SignalComponent):
            out.append(item)
            continue
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            data = {
                "name": getattr(item, "name", str(item)),
                "points": getattr(item, "points", None),
                "missing": bool(getattr(item, "missing", False)),
                "evidence_ids": list(getattr(item, "evidence_ids", []) or []),
            }
        name = data.get("name")
        if hasattr(name, "value"):
            name = name.value
        out.append(
            SignalComponent(
                name=str(name),
                points=data.get("points"),
                missing=bool(data.get("missing", False)),
                evidence_ids=list(data.get("evidence_ids") or []),
            )
        )
    return out


def signal_from_sofa(
    *,
    alert_id: str,
    score_result: Any,
    severity: str,
    rule_bundle_hash: str | None = None,
    resolution_state: ResolutionState = ResolutionState.OPEN,
) -> ClinicalSignal:
    """Project a SofaScoreResult (+ tier) onto the shared contract."""
    missing = [
        m.value if hasattr(m, "value") else str(m)
        for m in (score_result.missing_components or [])
    ]
    required = [
        "respiration",
        "coagulation",
        "liver",
        "cardiovascular",
        "cns",
        "renal",
    ]
    return ClinicalSignal(
        signal_id=alert_id,
        signal_type="sofa-deterioration",
        signal_kind=SignalKind.RISK,
        patient_id=score_result.patient_id,
        encounter_id=score_result.encounter_id,
        event_time=score_result.event_time,
        score=score_result.total_score,
        completeness=getattr(score_result.completeness, "value", score_result.completeness),
        severity=severity,
        required_inputs=required,
        missing_inputs=missing,
        evidence_ids=list(score_result.evidence_ids or []),
        rule_bundle_id=score_result.rule_bundle_id,
        rule_version=score_result.rule_version,
        rule_bundle_hash=rule_bundle_hash,
        resolution_state=resolution_state,
        components=_components_from_breakdown(list(score_result.components or [])),
    )


def signal_from_aki(
    *,
    alert_id: str,
    score_result: Any,
    severity: str,
    onset_time: datetime | None = None,
    criteria_met: list[str] | None = None,
    exclusions: list[str] | None = None,
    rule_bundle_hash: str | None = None,
    resolution_state: ResolutionState = ResolutionState.OPEN,
) -> ClinicalSignal:
    """Project an AkiScoreResult / timeline score onto the shared contract."""
    missing = list(score_result.missing_components or [])
    return ClinicalSignal(
        signal_id=alert_id,
        signal_type="aki",
        signal_kind=SignalKind.RISK,
        patient_id=score_result.patient_id,
        encounter_id=score_result.encounter_id,
        event_time=score_result.event_time,
        score=score_result.total_score,
        stage=getattr(score_result, "stage", None),
        completeness=getattr(score_result.completeness, "value", score_result.completeness),
        severity=severity,
        onset_time=onset_time,
        required_inputs=["creatinine", "baseline_creatinine", "urine_output"],
        missing_inputs=missing,
        evidence_ids=list(score_result.evidence_ids or []),
        exclusions=list(exclusions or []),
        criteria_met=list(criteria_met or []),
        rule_bundle_id=score_result.rule_bundle_id,
        rule_version=score_result.rule_version,
        rule_bundle_hash=rule_bundle_hash,
        resolution_state=resolution_state,
        components=_components_from_breakdown(list(score_result.components or [])),
        extensions={
            "creatinine_stage": getattr(score_result, "creatinine_stage", None),
            "urine_stage": getattr(score_result, "urine_stage", None),
        },
    )


def signal_from_respiratory(
    *,
    alert_id: str,
    score_result: Any,
    severity: str,
    rule_bundle_hash: str | None = None,
    resolution_state: ResolutionState = ResolutionState.OPEN,
) -> ClinicalSignal:
    """Project a RespScoreResult onto the shared contract."""
    missing = list(score_result.missing_components or [])
    return ClinicalSignal(
        signal_id=alert_id,
        signal_type="respiratory-deterioration",
        signal_kind=SignalKind.RISK,
        patient_id=score_result.patient_id,
        encounter_id=score_result.encounter_id,
        event_time=score_result.event_time,
        score=score_result.total_score,
        stage=getattr(score_result, "stage", None),
        completeness=getattr(score_result.completeness, "value", score_result.completeness),
        severity=severity,
        required_inputs=[
            "oxygenation",
            "respiratory_rate",
            "oxygen_support",
            "blood_gas",
        ],
        missing_inputs=missing,
        evidence_ids=list(score_result.evidence_ids or []),
        criteria_met=list(getattr(score_result, "criteria_met", None) or []),
        rule_bundle_id=score_result.rule_bundle_id,
        rule_version=score_result.rule_version,
        rule_bundle_hash=rule_bundle_hash,
        resolution_state=resolution_state,
        components=_components_from_breakdown(list(score_result.components or [])),
        extensions={
            "oxygenation_stage": getattr(score_result, "oxygenation_stage", None),
            "rate_stage": getattr(score_result, "rate_stage", None),
            "support_stage": getattr(score_result, "support_stage", None),
            "blood_gas_stage": getattr(score_result, "blood_gas_stage", None),
            "ratio_used": getattr(score_result, "ratio_used", None),
            "ratio_source": getattr(score_result, "ratio_source", None),
        },
    )


def signal_from_sepsis3(
    *,
    alert_id: str,
    patient_id: str,
    result: Any,
    event_time: datetime,
    encounter_id: str | None = None,
    severity: str = "none",
    resolution_state: ResolutionState = ResolutionState.OPEN,
) -> ClinicalSignal:
    """Project a Sepsis3Result onto the shared contract."""
    met = bool(getattr(result, "met", False))
    return ClinicalSignal(
        signal_id=alert_id,
        signal_type="sepsis-3",
        signal_kind=SignalKind.PHENOTYPE,
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_time=event_time,
        score=1 if met else 0,
        completeness=(
            "insufficient_data"
            if getattr(result, "status", None) == "insufficient_data"
            else "complete"
        ),
        severity=severity if met else "none",
        onset_time=getattr(result, "infection_time", None),
        required_inputs=["current_sofa", "baseline_sofa", "infection_suspicion"],
        missing_inputs=list(getattr(result, "missing_inputs", None) or []),
        evidence_ids=list(getattr(result, "evidence_ids", None) or []),
        exclusions=list(getattr(result, "exclusions_applied", None) or []),
        criteria_met=list(getattr(result, "criteria_met", None) or []),
        rule_bundle_id="sepsis-3-phenotype",
        rule_version=str(getattr(result, "phenotype_version", "1.0.0")),
        resolution_state=(
            ResolutionState.SUPPRESSED
            if getattr(result, "status", None) == "excluded"
            else resolution_state
        ),
        extensions={
            "phenotype_status": getattr(result, "status", None),
            "sofa_delta": getattr(result, "sofa_delta", None),
            "criteria_failed": list(getattr(result, "criteria_failed", None) or []),
        },
    )


def signal_from_alert_record(alert: Any) -> ClinicalSignal:
    """Normalize an AlertRecord / dict into ClinicalSignal (unknown types OK)."""
    if hasattr(alert, "model_dump"):
        data = alert.model_dump()
    else:
        data = dict(alert)

    if data.get("signal") and isinstance(data["signal"], dict):
        return ClinicalSignal.model_validate(data["signal"])

    signal_type = str(data.get("indicator") or "unknown")
    kind = data.get("signal_kind")
    if kind is None:
        kind = (
            SignalKind.PHENOTYPE
            if signal_type.endswith("-3") or signal_type == "sepsis-3"
            else SignalKind.RISK
        )
    else:
        kind = SignalKind(kind)

    resolution = data.get("resolution_state")
    if resolution is None:
        if data.get("suppressed"):
            resolution = ResolutionState.SUPPRESSED
        elif data.get("acknowledged"):
            resolution = ResolutionState.ACKNOWLEDGED
        else:
            resolution = ResolutionState.OPEN
    else:
        resolution = ResolutionState(resolution)

    return ClinicalSignal(
        signal_id=str(data["alert_id"]),
        signal_type=signal_type,
        signal_kind=kind,
        patient_id=str(data["patient_id"]),
        encounter_id=data.get("encounter_id"),
        event_time=data["event_time"],
        score=data.get("score"),
        stage=data.get("stage"),
        completeness=str(data.get("completeness") or "partial"),
        severity=str(data.get("tier") or "none"),
        onset_time=data.get("onset_time"),
        required_inputs=list(data.get("required_inputs") or []),
        missing_inputs=list(
            data.get("missing_inputs") or data.get("missing_components") or []
        ),
        evidence_ids=list(data.get("evidence_ids") or []),
        exclusions=list(data.get("exclusions") or []),
        criteria_met=list(data.get("criteria_met") or []),
        rule_bundle_id=str(data.get("rule_bundle_id") or "unknown"),
        rule_version=str(data.get("rule_version") or "0.0.0"),
        rule_bundle_hash=data.get("rule_bundle_hash"),
        resolution_state=resolution,
        components=_components_from_breakdown(
            list(data.get("component_breakdown") or [])
        ),
    )
