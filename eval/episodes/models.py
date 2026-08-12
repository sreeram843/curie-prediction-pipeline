"""Patient episode models (CURIE-012).

Prototype only — not clinically validated.

An episode groups correlated clinical signals for one patient (optionally one
encounter) into a single actionable unit with a dominant problem and supporting
differential context.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

EPISODE_SCHEMA_VERSION = "1.0.0"


class EpisodeStatus(StrEnum):
    OPEN = "open"
    UPDATED = "updated"
    ESCALATED = "escalated"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class EpisodeAction(StrEnum):
    """What the arbiter asks the page lane to do."""

    PAGE = "page"  # new interruptive actionability
    PASSIVE = "passive"  # visible update, no repeat page
    NONE = "none"  # no emission (e.g. duplicate within refractory)
    RESOLVE = "resolve"
    ACK = "ack"


# Higher = more dominant when ranking severity
SEVERITY_RANK: dict[str, int] = {
    "none": 0,
    "watch": 1,
    "urgent": 2,
    "critical": 3,
}

# Default dominance among equal-severity signal types
SIGNAL_PRIORITY: tuple[str, ...] = (
    "sepsis-3",
    "sofa-deterioration",
    "aki",
    "hypotension",
    "respiratory-deterioration",
)


class SignalRef(BaseModel):
    """One contributing clinical signal inside an episode."""

    signal_id: str
    signal_type: str
    signal_kind: str = "risk"
    severity: str = "none"
    score: int | None = None
    routing: Literal["interruptive", "passive", "none"] | None = None
    event_time: datetime
    evidence_ids: list[str] = Field(default_factory=list)
    suppressed: bool = False
    suppression_reason: str | None = None
    exclusions: list[str] = Field(default_factory=list)
    criteria_met: list[str] = Field(default_factory=list)
    rule_bundle_id: str | None = None
    rule_version: str | None = None


class EpisodeAuditEntry(BaseModel):
    at: datetime
    action: EpisodeAction
    status: EpisodeStatus
    reason: str
    signal_id: str | None = None
    dominant_signal_type: str | None = None


class Episode(BaseModel):
    schema_version: Literal["1.0.0"] = EPISODE_SCHEMA_VERSION
    episode_id: str
    patient_id: str
    encounter_id: str | None = None
    status: EpisodeStatus = EpisodeStatus.OPEN
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    acknowledged_at: datetime | None = None
    dominant_signal_type: str | None = None
    dominant_severity: str = "none"
    supporting_signal_types: list[str] = Field(default_factory=list)
    signals: list[SignalRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    page_count: int = 0
    passive_update_count: int = 0
    last_page_at: datetime | None = None
    last_action: EpisodeAction = EpisodeAction.NONE
    last_action_reason: str = ""
    audit: list[EpisodeAuditEntry] = Field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
