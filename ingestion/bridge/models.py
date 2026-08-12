"""Trusted clinical-fact envelope models (CURIE-022)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

BRIDGE_SCHEMA_VERSION = "1.0.0"

TrustStatus = Literal["candidate", "trusted", "quarantined", "rejected"]
CheckResult = Literal["passed", "failed", "not_required", "pending"]
ExtractionMethod = Literal["deterministic", "llm", "human_review", "hybrid"]


class SourceSpan(BaseModel):
    start: int | None = None
    end: int | None = None
    text: str | None = None
    path: str | None = None


class SourceRef(BaseModel):
    system: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    spans: list[SourceSpan] = Field(default_factory=list)


class ExtractionProvenance(BaseModel):
    method: ExtractionMethod
    model: str | None = None
    prompt_version: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _llm_fields(self) -> ExtractionProvenance:
        if self.method == "llm":
            if not self.model:
                raise ValueError("LLM extraction requires model")
            if not self.prompt_version:
                raise ValueError("LLM extraction requires prompt_version")
        return self


class ValidationResults(BaseModel):
    model_config = {"populate_by_name": True}

    schema_status: CheckResult = Field(alias="schema")
    terminology: CheckResult
    provenance: CheckResult
    semantic_review: CheckResult = "not_required"


class TrustedClinicalFactEnvelope(BaseModel):
    """Cross-project clinical fact published by curie-fhir / consumed here."""

    schema_version: Literal["1.0.0"] = BRIDGE_SCHEMA_VERSION
    event_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    encounter_id: str | None = None
    resource_type: str = Field(min_length=1)
    resource: dict[str, Any] = Field(default_factory=dict)
    clinical_event_time: datetime
    availability_time: datetime
    trust_status: TrustStatus
    source: SourceRef
    extraction: ExtractionProvenance
    validation: ValidationResults
    idempotency_key: str = Field(min_length=1)
    # Optional audit tags (never used for ordering)
    extensions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("patient_id")
    @classmethod
    def _patient_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("patient_id required")
        return cleaned

    def is_llm_derived(self) -> bool:
        return self.extraction.method in {"llm", "hybrid"}

    def is_deterministic(self) -> bool:
        return self.extraction.method == "deterministic"

    def audit_record(self) -> dict[str, Any]:
        """Compact audit row distinguishing LLM vs deterministic facts."""
        return {
            "event_id": self.event_id,
            "idempotency_key": self.idempotency_key,
            "trust_status": self.trust_status,
            "extraction_method": self.extraction.method,
            "extraction_model": self.extraction.model,
            "prompt_version": self.extraction.prompt_version,
            "is_llm_derived": self.is_llm_derived(),
            "is_deterministic": self.is_deterministic(),
            "validation": self.validation.model_dump(by_alias=True),
            "source_system": self.source.system,
            "source_resource_id": self.source.resource_id,
            "clinical_event_time": self.clinical_event_time.isoformat(),
            "availability_time": self.availability_time.isoformat(),
        }
