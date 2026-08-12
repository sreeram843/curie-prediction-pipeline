"""MIMIC timeline events → canonical envelopes (CURIE-015)."""

from __future__ import annotations

from datetime import UTC, datetime

from ingestion.adapters.mimic.timeline import ADAPTER_VERSION, MimicTimelineEvent
from ingestion.envelope.models import CanonicalEventEnvelope, Provenance


def _observation_resource(event: MimicTimelineEvent) -> dict:
    coding = []
    if event.code:
        coding.append(
            {
                "system": event.code_system or "http://loinc.org",
                "code": event.code,
                "display": event.display,
            }
        )
    resource: dict = {
        "resourceType": "Observation",
        "id": event.evidence_id.replace("/", "-"),
        "status": event.status,
        "code": {"coding": coding} if coding else {"text": event.display or "mimic"},
        "subject": {"reference": f"Patient/{event.subject_id}"},
        "effectiveDateTime": event.event_time.isoformat(),
        "issued": event.availability_time.isoformat(),
    }
    if event.hadm_id:
        resource["encounter"] = {"reference": f"Encounter/{event.hadm_id}"}
    if event.valuenum is not None:
        resource["valueQuantity"] = {
            "value": event.valuenum,
            "unit": event.unit,
            "system": "http://unitsofmeasure.org",
            "code": event.unit,
        }
    if event.itemid is not None:
        resource["identifier"] = [
            {
                "system": "https://mimic.mit.edu/itemid",
                "value": str(event.itemid),
            }
        ]
    return resource


def _condition_resource(event: MimicTimelineEvent) -> dict:
    coding = []
    if event.code:
        coding.append(
            {
                "system": event.code_system or "http://hl7.org/fhir/sid/icd-10",
                "code": event.code,
                "display": event.display,
            }
        )
    resource: dict = {
        "resourceType": "Condition",
        "id": event.evidence_id.replace("/", "-"),
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "code": {"coding": coding} if coding else {"text": event.display or "condition"},
        "subject": {"reference": f"Patient/{event.subject_id}"},
        "onsetDateTime": event.event_time.isoformat(),
        "recordedDate": event.availability_time.isoformat(),
    }
    if event.is_discharge_diagnosis:
        resource["category"] = [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "encounter-diagnosis",
                    }
                ],
                "text": "discharge_diagnosis",
            }
        ]
    return resource


def event_to_envelope(
    event: MimicTimelineEvent,
    *,
    ingest_time: datetime | None = None,
) -> CanonicalEventEnvelope:
    now = ingest_time or datetime.now(UTC)
    if event.kind == "condition":
        resource = _condition_resource(event)
        rtype = "Condition"
    else:
        resource = _observation_resource(event)
        rtype = "Observation"
    return CanonicalEventEnvelope(
        patient_id=f"Patient/{event.subject_id}",
        encounter_id=f"Encounter/{event.hadm_id}" if event.hadm_id else None,
        resource_type=rtype,  # type: ignore[arg-type]
        resource=resource,
        event_time=event.event_time,
        ingest_time=now,
        availability_time=event.availability_time,
        source="mimic",
        idempotency_key=event.evidence_id,
        provenance=Provenance(
            adapter="mimic",
            adapter_version=ADAPTER_VERSION,
            raw_ref=event.raw_ref or event.evidence_id,
        ),
    )


def events_to_envelopes(
    events: list[MimicTimelineEvent],
    *,
    ingest_time: datetime | None = None,
) -> list[CanonicalEventEnvelope]:
    envs = [event_to_envelope(e, ingest_time=ingest_time) for e in events]
    envs.sort(
        key=lambda e: (
            e.effective_availability_time(),
            e.event_time,
            e.idempotency_key,
        )
    )
    return envs
