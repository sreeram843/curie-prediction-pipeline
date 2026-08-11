"""Guarded Reasoning Pipeline models — additive narrative only."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class NarrativeDraft(BaseModel):
    summary: str
    claims: list[Claim] = Field(default_factory=list)
    abstain: bool = False
    abstain_reason: str | None = None
    model_name: str = "curie-grp-stub-v1"


class ValidatedClaim(BaseModel):
    text: str
    evidence_ids: list[str]
    grounded: bool
    failure_reason: str | None = None


class GateDecision(BaseModel):
    status: Literal["pass", "quarantine", "abstain", "disabled", "error"]
    narrative: str | None = None
    claims: list[ValidatedClaim] = Field(default_factory=list)
    quarantine_reason: str | None = None
    model_name: str | None = None
    alert_id: str
    # Explicit: GRP never mutates score/tier
    score_unchanged: bool = True


class AlertContext(BaseModel):
    alert_id: str
    patient_id: str
    score: int | None
    tier: str
    completeness: str
    evidence_ids: list[str]
    component_breakdown: list[dict]
    missing_components: list[str]
    rule_bundle_id: str
    rule_version: str
