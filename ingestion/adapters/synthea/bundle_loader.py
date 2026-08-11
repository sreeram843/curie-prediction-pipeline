"""Synthea FHIR bundle → canonical envelopes (no Kafka yet)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from ingestion.envelope.models import CanonicalEventEnvelope, Provenance, ResourceType

SUPPORTED: set[str] = {
    "Observation",
    "Condition",
    "MedicationAdministration",
    "MedicationRequest",
    "Procedure",
    "Encounter",
    "Patient",
    "DiagnosticReport",
}

ADAPTER_VERSION = "0.1.0"


def _parse_resource_time(resource: dict[str, Any]) -> datetime | None:
    for key in ("effectiveDateTime", "authoredOn", "onsetDateTime", "period"):
        val = resource.get(key)
        if isinstance(val, str):
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        if isinstance(val, dict) and isinstance(val.get("start"), str):
            return datetime.fromisoformat(val["start"].replace("Z", "+00:00"))
    meta = resource.get("meta") or {}
    if isinstance(meta.get("lastUpdated"), str):
        return datetime.fromisoformat(meta["lastUpdated"].replace("Z", "+00:00"))
    return None


def _patient_id(resource: dict[str, Any], bundle_patient: str | None) -> str | None:
    if resource.get("resourceType") == "Patient":
        rid = resource.get("id")
        return f"Patient/{rid}" if rid else bundle_patient
    subject = resource.get("subject") or resource.get("patient") or {}
    ref = subject.get("reference") if isinstance(subject, dict) else None
    return ref or bundle_patient


def _encounter_id(resource: dict[str, Any]) -> str | None:
    enc = resource.get("encounter") or {}
    if isinstance(enc, dict):
        return enc.get("reference")
    return None


def _idempotency_key(resource: dict[str, Any], source_path: str) -> str:
    rid = resource.get("id") or ""
    rtype = resource.get("resourceType") or ""
    version = (resource.get("meta") or {}).get("versionId") or "0"
    raw = f"{source_path}|{rtype}|{rid}|{version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def iter_bundle_resources(path: Path) -> Iterator[dict[str, Any]]:
    data = orjson.loads(path.read_bytes())
    if data.get("resourceType") == "Bundle":
        for entry in data.get("entry") or []:
            res = entry.get("resource")
            if isinstance(res, dict):
                yield res
    elif data.get("resourceType"):
        yield data


def find_bundle_patient_id(path: Path) -> str | None:
    for res in iter_bundle_resources(path):
        if res.get("resourceType") == "Patient" and res.get("id"):
            return f"Patient/{res['id']}"
    return None


def resource_to_envelope(
    resource: dict[str, Any],
    *,
    source_path: str,
    ingest_time: datetime | None = None,
    bundle_patient: str | None = None,
    event_time_override: datetime | None = None,
) -> CanonicalEventEnvelope | None:
    rtype = resource.get("resourceType")
    if rtype not in SUPPORTED:
        return None
    patient_id = _patient_id(resource, bundle_patient)
    if not patient_id:
        return None
    event_time = event_time_override or _parse_resource_time(resource) or (
        ingest_time or datetime.now(UTC)
    )
    now = ingest_time or datetime.now(UTC)
    return CanonicalEventEnvelope(
        patient_id=patient_id,
        encounter_id=_encounter_id(resource),
        resource_type=rtype,  # type: ignore[arg-type]
        resource=resource,
        event_time=event_time,
        ingest_time=now,
        source="synthea",
        idempotency_key=_idempotency_key(resource, source_path),
        provenance=Provenance(
            adapter="synthea",
            adapter_version=ADAPTER_VERSION,
            raw_ref=source_path,
        ),
    )


def load_envelopes_from_dir(
    fhir_dir: Path,
    *,
    ingest_time: datetime | None = None,
) -> list[CanonicalEventEnvelope]:
    envelopes: list[CanonicalEventEnvelope] = []
    paths = sorted(fhir_dir.glob("*.json"))
    for path in paths:
        bundle_patient = find_bundle_patient_id(path)
        for resource in iter_bundle_resources(path):
            env = resource_to_envelope(
                resource,
                source_path=str(path),
                ingest_time=ingest_time,
                bundle_patient=bundle_patient,
            )
            if env is not None:
                envelopes.append(env)
    envelopes.sort(key=lambda e: (e.event_time, e.patient_id, e.idempotency_key))
    return envelopes


def topic_for_resource(resource_type: ResourceType | str) -> str:
    if resource_type == "Observation":
        return "observations"
    if resource_type == "Condition":
        return "conditions"
    if resource_type in {"MedicationAdministration", "MedicationRequest"}:
        return "medications"
    return "observations"
