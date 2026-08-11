"""T4 labeled-note fixtures for extraction accuracy."""

from __future__ import annotations

from ingestion.extraction.adapter import extract_note_to_fhir
from ingestion.extraction.deterministic import extract_deterministic

NOTE_SEPSISISH = """
ICU progress note: Patient febrile. Platelets 42 x10^9/L. Total bilirubin 2.6 mg/dL.
Creatinine 2.2 mg/dL. MAP 64 mmHg. GCS 13. Plan: cultures, fluids.
"""

NOTE_AMBIGUOUS = """
Nursing note: Patient feels unwell today. Family at bedside. Will reassess later.
"""


def test_deterministic_extracts_sofa_relevant_labs() -> None:
    result = extract_deterministic(
        NOTE_SEPSISISH, note_id="note-t4-001", patient_id="Patient/t4-001"
    )
    assert result.status == "ok"
    loincs = {o.loinc for o in result.observations}
    assert {"777-3", "1975-2", "2160-0", "8478-0", "9269-2"} <= loincs
    assert all(r["resourceType"] == "Observation" for r in result.fhir_resources)
    assert all(o.evidence_span is not None for o in result.observations)


def test_abstain_on_ambiguous_note() -> None:
    result = extract_deterministic(NOTE_AMBIGUOUS, note_id="note-t4-002")
    assert result.status == "abstain"
    assert result.observations == []


def test_feature_flag_disables_by_default() -> None:
    result = extract_note_to_fhir(NOTE_SEPSISISH, note_id="note-t4-003")
    assert result.status == "disabled"


def test_force_bypasses_flag_for_eval() -> None:
    result = extract_note_to_fhir(NOTE_SEPSISISH, note_id="note-t4-004", force=True)
    assert result.status == "ok"
