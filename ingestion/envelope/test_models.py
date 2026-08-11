from datetime import UTC, datetime

from ingestion.envelope.models import CanonicalEventEnvelope, Provenance


def test_canonical_envelope_roundtrip() -> None:
    now = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    env = CanonicalEventEnvelope(
        patient_id="Patient/abc",
        encounter_id="Encounter/1",
        resource_type="Observation",
        resource={"resourceType": "Observation", "id": "obs-1", "status": "final"},
        event_time=now,
        ingest_time=now,
        source="synthea",
        idempotency_key="obs-1:final",
        provenance=Provenance(adapter="synthea", adapter_version="0.1.0"),
    )
    data = env.model_dump(mode="json")
    again = CanonicalEventEnvelope.model_validate(data)
    assert again.patient_id == "Patient/abc"
    assert again.schema_version == "1.0.0"
