"""Alert domain models for the action API (CURIE-010 clinical-signal contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from eval.signals.contract import ClinicalSignal, signal_from_alert_record


class ComponentBreakdown(BaseModel):
    name: str
    points: int | None = None
    missing: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class AlertRecord(BaseModel):
    alert_id: str
    patient_id: str
    patient_name: str | None = None
    encounter_id: str | None = None
    # Open string so unknown future indicators render without API changes.
    indicator: str = "sofa-deterioration"
    signal_kind: Literal["risk", "phenotype"] = "risk"
    event_time: datetime
    ingest_time: datetime | None = None
    score: int | None = None
    stage: int | None = None
    completeness: str = "partial"
    tier: str = "none"
    onset_time: datetime | None = None
    required_inputs: list[str] = Field(default_factory=list)
    component_breakdown: list[ComponentBreakdown] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    criteria_met: list[str] = Field(default_factory=list)
    rule_bundle_id: str = "sepsis-sofa"
    rule_version: str = "0.1.0"
    rule_bundle_hash: str | None = None
    resolution_state: Literal["open", "acknowledged", "resolved", "suppressed"] = "open"
    governance_path: Literal["naive", "governed"] = "governed"
    suppressed: bool = False
    suppression_reason: str | None = None
    routing: Literal["interruptive", "passive", "none"] | None = None
    page_deferred_reason: str | None = None
    positive_components: int | None = None
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledge_note: str | None = None
    # Nested contract projection (same top-level schema for every indicator)
    signal: ClinicalSignal | None = None
    # Phase 2 GRP — additive only; never changes score/tier
    narrative_status: (
        Literal["none", "pass", "quarantine", "abstain", "disabled", "error"] | None
    ) = "none"
    narrative: str | None = None
    narrative_claims: list[dict[str, Any]] = Field(default_factory=list)
    quarantine_reason: str | None = None
    grp_model_name: str | None = None

    @field_validator("indicator")
    @classmethod
    def _indicator_nonempty(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("indicator must be a non-empty signal_type")
        return cleaned

    @model_validator(mode="after")
    def _sync_signal_and_resolution(self) -> AlertRecord:
        resolution = self.resolution_state
        if self.suppressed:
            resolution = "suppressed"
        elif self.acknowledged:
            resolution = "acknowledged"
        object.__setattr__(self, "resolution_state", resolution)

        if self.signal is None:
            projected = signal_from_alert_record(self)
            object.__setattr__(self, "signal", projected)
            if not self.signal_kind:
                object.__setattr__(self, "signal_kind", projected.signal_kind.value)
        return self


class AcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class AcknowledgeResponse(BaseModel):
    alert_id: str
    acknowledged: bool
    acknowledged_at: datetime


class MetricsSummary(BaseModel):
    total_alerts: int
    open_alerts: int
    acknowledged_alerts: int
    by_tier: dict[str, int]
    by_routing: dict[str, int] = Field(default_factory=dict)
    by_indicator: dict[str, int] = Field(default_factory=dict)


def alert_from_dict(data: dict[str, Any]) -> AlertRecord:
    return AlertRecord.model_validate(data)
