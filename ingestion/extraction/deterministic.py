"""Deterministic note → Observation extractor for T4 fixtures / offline eval.

Uses regex patterns over synthetic notes. Not clinically validated.
Real LLM backends plug in behind the same interface later.
"""

from __future__ import annotations

import re
from typing import Any

from ingestion.extraction.models import ExtractedObservation, ExtractionResult, ExtractionSpan

# (label, loinc, pattern, unit, value group index)
_PATTERNS: list[tuple[str, str, re.Pattern[str], str | None, int]] = [
    (
        "Platelets",
        "777-3",
        re.compile(
            r"platelets?\s*(?:count)?\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*(x?10\^?9/?[lL])?",
            re.I,
        ),
        "10*9/L",
        1,
    ),
    (
        "Bilirubin",
        "1975-2",
        re.compile(r"(?:total\s+)?bilirubin\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*mg/?dL", re.I),
        "mg/dL",
        1,
    ),
    (
        "Creatinine",
        "2160-0",
        re.compile(r"creatinine\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*mg/?dL", re.I),
        "mg/dL",
        1,
    ),
    (
        "GCS",
        "9269-2",
        re.compile(r"(?:GCS|Glasgow\s+Coma\s+Scale)\s*(?:of|=|:)?\s*(\d{1,2})", re.I),
        None,
        1,
    ),
    (
        "MAP",
        "8478-0",
        re.compile(
            r"(?:MAP|mean\s+arterial\s+pressure)\s*(?:of|=|:)?\s*(\d+(?:\.\d+)?)\s*mmHg",
            re.I,
        ),
        "mmHg",
        1,
    ),
]


def _to_fhir_observation(
    *,
    note_id: str,
    patient_id: str | None,
    obs: ExtractedObservation,
    index: int,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Observation",
        "id": f"extract-{note_id}-{index}",
        "status": "final",
        "code": {
            "coding": (
                [{"system": "http://loinc.org", "code": obs.loinc, "display": obs.display}]
                if obs.loinc
                else []
            ),
            "text": obs.display,
        },
        "valueQuantity": {"value": obs.value, "unit": obs.unit} if obs.value is not None else None,
    }
    if patient_id:
        resource["subject"] = {"reference": patient_id}
    # Strip null valueQuantity for cleaner fixtures
    if resource["valueQuantity"] is None:
        resource.pop("valueQuantity")
    return resource


def extract_deterministic(
    note_text: str,
    *,
    note_id: str,
    patient_id: str | None = None,
) -> ExtractionResult:
    text = note_text or ""
    if not text.strip():
        return ExtractionResult(
            status="abstain",
            note_id=note_id,
            patient_id=patient_id,
            message="Empty note — insufficient grounded evidence for extraction.",
            backend="deterministic",
        )

    observations: list[ExtractedObservation] = []
    for display, loinc, pattern, unit, group in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = float(match.group(group))
        span = ExtractionSpan(start=match.start(), end=match.end(), text=match.group(0))
        observations.append(
            ExtractedObservation(
                loinc=loinc,
                display=display,
                value=value,
                unit=unit,
                evidence_span=span,
                confidence=0.85,
            )
        )

    if not observations:
        return ExtractionResult(
            status="abstain",
            note_id=note_id,
            patient_id=patient_id,
            message="Insufficient grounded evidence for extraction.",
            backend="deterministic",
        )

    fhir = [
        _to_fhir_observation(note_id=note_id, patient_id=patient_id, obs=o, index=i)
        for i, o in enumerate(observations)
    ]
    return ExtractionResult(
        status="ok",
        note_id=note_id,
        patient_id=patient_id,
        observations=observations,
        fhir_resources=fhir,
        backend="deterministic",
    )
