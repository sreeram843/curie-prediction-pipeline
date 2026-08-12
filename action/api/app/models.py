"""Alert domain models for the action API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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
    indicator: Literal["sepsis", "aki"] = "sepsis"
    event_time: datetime
    ingest_time: datetime | None = None
    score: int | None = None
    completeness: str = "partial"
    tier: str = "none"
    component_breakdown: list[ComponentBreakdown] = Field(default_factory=list)
    missing_components: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_bundle_id: str = "sepsis-sofa"
    rule_version: str = "0.1.0"
    governance_path: Literal["naive", "governed"] = "governed"
    suppressed: bool = False
    suppression_reason: str | None = None
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledge_note: str | None = None
    # Phase 2 GRP — additive only; never changes score/tier
    narrative_status: (
        Literal["none", "pass", "quarantine", "abstain", "disabled", "error"] | None
    ) = "none"
    narrative: str | None = None
    narrative_claims: list[dict[str, Any]] = Field(default_factory=list)
    quarantine_reason: str | None = None
    grp_model_name: str | None = None


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


def alert_from_dict(data: dict[str, Any]) -> AlertRecord:
    return AlertRecord.model_validate(data)
