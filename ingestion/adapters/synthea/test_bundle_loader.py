"""Unit tests for Synthea bundle → envelope conversion."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ingestion.adapters.synthea.bundle_loader import resource_to_envelope


def test_observation_to_envelope(tmp_path: Path) -> None:
    resource = {
        "resourceType": "Observation",
        "id": "obs-1",
        "status": "final",
        "effectiveDateTime": "2024-01-02T03:04:05Z",
        "subject": {"reference": "Patient/p1"},
        "encounter": {"reference": "Encounter/e1"},
        "code": {"coding": [{"system": "http://loinc.org", "code": "777-3"}]},
    }
    env = resource_to_envelope(
        resource,
        source_path=str(tmp_path / "bundle.json"),
        ingest_time=datetime(2024, 1, 3, tzinfo=UTC),
    )
    assert env is not None
    assert env.patient_id == "Patient/p1"
    assert env.encounter_id == "Encounter/e1"
    assert env.resource_type == "Observation"
    assert env.event_time.year == 2024
    assert env.source == "synthea"
    assert env.provenance.adapter == "synthea"
