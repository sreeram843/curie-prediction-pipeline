"""Trusted clinical-fact bridge (CURIE-022).

Shared envelope between ``curie-fhir`` (producer) and this pipeline (consumer).
Only ``trust_status=trusted`` facts with passed validation may mutate scoring.
"""

from __future__ import annotations

from ingestion.bridge.adapter import trusted_fact_to_canonical
from ingestion.bridge.gate import AdmissionDecision, admit_trusted_fact
from ingestion.bridge.models import (
    BRIDGE_SCHEMA_VERSION,
    ExtractionProvenance,
    SourceRef,
    TrustedClinicalFactEnvelope,
    ValidationResults,
)

__all__ = [
    "BRIDGE_SCHEMA_VERSION",
    "AdmissionDecision",
    "ExtractionProvenance",
    "SourceRef",
    "TrustedClinicalFactEnvelope",
    "ValidationResults",
    "admit_trusted_fact",
    "trusted_fact_to_canonical",
]
