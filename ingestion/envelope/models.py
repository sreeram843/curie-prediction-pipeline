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
    # When the fact became knowable to the system (CURIE-015 / protocol order key).
    # Optional for backward compatibility; when absent, treat as event_time.
    availability_time: datetime | None = None
    source: str
    idempotency_key: str = Field(min_length=1)
    provenance: Provenance

    def effective_availability_time(self) -> datetime:
        """Availability clock used for leakage-safe replay ordering."""
        return self.availability_time if self.availability_time is not None else self.event_time
