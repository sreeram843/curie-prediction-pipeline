"""Public extraction adapter — feature-flagged, never on the alert critical path."""

from __future__ import annotations

from ingestion.extraction.deterministic import extract_deterministic
from ingestion.extraction.models import ExtractionResult
from ingestion.extraction.settings import settings


def extract_note_to_fhir(
    note_text: str,
    *,
    note_id: str,
    patient_id: str | None = None,
    force: bool = False,
) -> ExtractionResult:
    """Extract Observations from unstructured text.

    When ``CURIE_ENABLE_EXTRACTION`` is false (default), returns ``disabled``
    unless ``force=True`` (tests / explicit eval runs).
    """
    if not settings.enable_extraction and not force:
        return ExtractionResult(
            status="disabled",
            note_id=note_id,
            patient_id=patient_id,
            message="Extraction adapter disabled (CURIE_ENABLE_EXTRACTION=false).",
            backend=settings.extraction_backend,
        )

    if settings.extraction_backend != "deterministic":
        return ExtractionResult(
            status="error",
            note_id=note_id,
            patient_id=patient_id,
            message=f"Unsupported extraction backend: {settings.extraction_backend}",
            backend=settings.extraction_backend,
        )

    return extract_deterministic(note_text, note_id=note_id, patient_id=patient_id)
