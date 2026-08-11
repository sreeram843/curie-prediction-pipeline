"""Canonical event envelope models (Phase 0 stub; validated in Phase 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ResourceType = Literal[
    "Observation",
    "Condition",
    "MedicationAdministration",
    "MedicationRequest",
    "Procedure",
    "Encounter",
    "Patient",
    "DiagnosticReport",
]


class Provenance(BaseModel):
    adapter: str
    adapter_version: str
    raw_ref: str | None = None


class CanonicalEventEnvelope(BaseModel):
    """Kafka payload wrapper for every clinical resource event."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    patient_id: str
    encounter_id: str | None = None
    resource_type: ResourceType
    resource: dict[str, Any]
    event_time: datetime
    ingest_time: datetime
    source: str
    idempotency_key: str = Field(min_length=1)
    provenance: Provenance
