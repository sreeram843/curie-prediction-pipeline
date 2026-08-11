"""Text → FHIR extraction models (Phase 2). Output is never used to fire alerts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractionSpan(BaseModel):
    start: int
    end: int
    text: str


class ExtractedObservation(BaseModel):
    loinc: str | None = None
    display: str
    value: float | None = None
    unit: str | None = None
    evidence_span: ExtractionSpan | None = None
    confidence: float = Field(ge=0, le=1, default=0.5)


class ExtractionResult(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["ok", "abstain", "disabled", "error"]
    note_id: str
    patient_id: str | None = None
    observations: list[ExtractedObservation] = Field(default_factory=list)
    fhir_resources: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None
    backend: str = "deterministic"
