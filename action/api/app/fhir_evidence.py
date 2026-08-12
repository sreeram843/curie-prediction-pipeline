"""FHIR-compatible evidence references (CURIE-019).

Maps Curie ``evidence_ids`` onto FHIR R4 ``Reference`` objects and a small
read-only Bundle. Scoring / governance code never imports EHR adapters; this
module is presentation-only.
"""

from __future__ import annotations

import re
from typing import Any

from action.api.app.models import AlertRecord

# FHIR R4 resource types we commonly see in Synthea / MIMIC-shaped evidence ids.
_KNOWN_TYPES = frozenset(
    {
        "Observation",
        "Condition",
        "Procedure",
        "MedicationAdministration",
        "MedicationRequest",
        "DiagnosticReport",
        "DocumentReference",
        "Encounter",
        "Patient",
        "Specimen",
        "ServiceRequest",
        "Device",
    }
)

_FHIR_REF = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z0-9]+)/(?P<id>[A-Za-z0-9\-\.]{1,64})$"
)

EVIDENCE_SYSTEM = "urn:curie:evidence-id"


def patient_reference(patient_id: str | None) -> str:
    """Return a FHIR Patient reference without doubling the ``Patient/`` prefix."""
    raw = (patient_id or "").strip()
    if not raw:
        return "Patient/unknown"
    if raw.startswith("Patient/"):
        return raw
    return f"Patient/{raw}"


def parse_evidence_id(evidence_id: str) -> dict[str, Any]:
    """Return a FHIR R4 Reference-shaped dict for one evidence id."""
    raw = (evidence_id or "").strip()
    if not raw:
        raise ValueError("evidence_id must be non-empty")

    match = _FHIR_REF.match(raw)
    if match and match.group("type") in _KNOWN_TYPES:
        rtype = match.group("type")
        rid = match.group("id")
        return {
            "reference": f"{rtype}/{rid}",
            "type": rtype,
            "display": raw,
        }

    # Non-canonical ids (e.g. lab/plt-1, chart/map-low) stay addressable via
    # identifier without inventing a fake FHIR resource path.
    inferred = "Observation"
    prefix = raw.split("/", 1)[0].lower() if "/" in raw else ""
    if prefix in {"dx", "condition"}:
        inferred = "Condition"
    elif prefix in {"note", "doc"}:
        inferred = "DocumentReference"
    elif prefix in {"enc", "encounter"}:
        inferred = "Encounter"
    elif prefix in {"med", "drug"}:
        inferred = "MedicationAdministration"

    return {
        "type": inferred,
        "identifier": {"system": EVIDENCE_SYSTEM, "value": raw},
        "display": raw,
    }


def fhir_references_for_alert(alert: AlertRecord) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for eid in alert.evidence_ids:
        key = eid.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        refs.append(parse_evidence_id(key))
    for comp in alert.component_breakdown:
        for eid in comp.evidence_ids:
            key = eid.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            refs.append(parse_evidence_id(key))
    return refs


def evidence_bundle_for_alert(alert: AlertRecord) -> dict[str, Any]:
    """Minimal FHIR Bundle wrapping References (not full clinical resources)."""
    refs = fhir_references_for_alert(alert)
    entries = []
    for i, ref in enumerate(refs):
        entries.append(
            {
                "fullUrl": f"urn:uuid:curie-evidence-{alert.alert_id}-{i}",
                "resource": {
                    "resourceType": "Basic",
                    "id": f"evidence-{i}",
                    "code": {
                        "coding": [
                            {
                                "system": "urn:curie:code",
                                "code": "evidence-pointer",
                                "display": "Curie evidence pointer",
                            }
                        ]
                    },
                    "subject": {"reference": patient_reference(alert.patient_id)},
                    "extension": [
                        {
                            "url": "https://curie.local/fhir/StructureDefinition/evidence-reference",
                            "valueReference": ref,
                        }
                    ],
                },
            }
        )
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "id": f"evidence-{alert.alert_id}",
        "meta": {
            "tag": [
                {
                    "system": "urn:curie:rule-bundle",
                    "code": alert.rule_bundle_id,
                    "display": alert.rule_version,
                }
            ]
        },
        "entry": entries,
        "extension": [
            {
                "url": "https://curie.local/fhir/StructureDefinition/alert-id",
                "valueString": alert.alert_id,
            },
            {
                "url": "https://curie.local/fhir/StructureDefinition/rule-bundle-hash",
                "valueString": alert.rule_bundle_hash or "",
            },
        ],
    }
