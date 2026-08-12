"""Adapt admitted trusted facts onto CanonicalEventEnvelope for scoring."""

from __future__ import annotations

from datetime import UTC, datetime

from ingestion.bridge.gate import AdmissionDecision, admit_trusted_fact
from ingestion.bridge.models import TrustedClinicalFactEnvelope
from ingestion.envelope.models import CanonicalEventEnvelope, Provenance


def trusted_fact_to_canonical(
    fact: TrustedClinicalFactEnvelope,
    *,
    ingest_time: datetime | None = None,
) -> CanonicalEventEnvelope:
    """Map a trusted fact to the Kafka scoring envelope.

    Callers must only invoke this after ``admit_trusted_fact`` returns admit.
    """
    if fact.trust_status != "trusted":
        raise ValueError("only trusted facts may become canonical scoring events")
    rtype = fact.resource_type
    # Narrow to ResourceType literal used by CanonicalEventEnvelope
    allowed = {
        "Observation",
        "Condition",
        "MedicationAdministration",
        "MedicationRequest",
        "Procedure",
        "Encounter",
        "Patient",
        "DiagnosticReport",
    }
    if rtype not in allowed:
        raise ValueError(f"resource_type {rtype} not supported for scoring envelope")
    method = fact.extraction.method
    return CanonicalEventEnvelope(
        patient_id=fact.patient_id,
        encounter_id=fact.encounter_id,
        resource_type=rtype,  # type: ignore[arg-type]
        resource=dict(fact.resource),
        event_time=fact.clinical_event_time,
        ingest_time=ingest_time or datetime.now(UTC),
        availability_time=fact.availability_time,
        source=fact.source.system,
        idempotency_key=fact.idempotency_key,
        provenance=Provenance(
            adapter=f"trusted-fact-bridge/{method}",
            adapter_version=fact.schema_version,
            raw_ref=fact.source.resource_id,
        ),
    )


def admit_and_canonicalize(
    payload: dict | TrustedClinicalFactEnvelope,
    *,
    clock: datetime | None = None,
    ingest_time: datetime | None = None,
) -> tuple[AdmissionDecision, CanonicalEventEnvelope | None]:
    """Single entry: gate then optionally produce a scoring envelope."""
    decision = admit_trusted_fact(payload, clock=clock)
    if not decision.may_mutate_scoring or decision.fact is None:
        return decision, None
    return decision, trusted_fact_to_canonical(decision.fact, ingest_time=ingest_time)
