"""Admission gate for trusted clinical facts (CURIE-022).

Reject / quarantine candidates, unknown schemas, failed validation, missing
provenance, and future-availability events. Only trusted facts may score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ingestion.bridge.models import BRIDGE_SCHEMA_VERSION, TrustedClinicalFactEnvelope

KNOWN_RESOURCE_TYPES = frozenset(
    {
        "Observation",
        "Condition",
        "MedicationAdministration",
        "MedicationRequest",
        "Procedure",
        "Encounter",
        "Patient",
        "DiagnosticReport",
        "DocumentReference",
    }
)

AdmissionOutcome = Literal["admit", "quarantine", "reject"]


@dataclass(frozen=True)
class AdmissionDecision:
    outcome: AdmissionOutcome
    reason: str
    fact: TrustedClinicalFactEnvelope | None
    audit: dict[str, Any]
    may_mutate_scoring: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "may_mutate_scoring": self.may_mutate_scoring,
            "event_id": self.fact.event_id if self.fact else None,
            "audit": self.audit,
        }


def _reject(
    reason: str,
    *,
    fact: TrustedClinicalFactEnvelope | None = None,
    audit: dict[str, Any] | None = None,
) -> AdmissionDecision:
    return AdmissionDecision(
        outcome="reject",
        reason=reason,
        fact=fact,
        audit=audit or (fact.audit_record() if fact else {}),
        may_mutate_scoring=False,
    )


def _quarantine(
    reason: str,
    fact: TrustedClinicalFactEnvelope,
) -> AdmissionDecision:
    return AdmissionDecision(
        outcome="quarantine",
        reason=reason,
        fact=fact,
        audit=fact.audit_record(),
        may_mutate_scoring=False,
    )


def _admit(fact: TrustedClinicalFactEnvelope) -> AdmissionDecision:
    return AdmissionDecision(
        outcome="admit",
        reason="trusted_validation_passed",
        fact=fact,
        audit=fact.audit_record(),
        may_mutate_scoring=True,
    )


def parse_fact_payload(payload: dict[str, Any]) -> TrustedClinicalFactEnvelope | AdmissionDecision:
    """Parse unknown payload; unknown schema → reject without mutating scoring."""
    version = str(payload.get("schema_version") or "")
    if version != BRIDGE_SCHEMA_VERSION:
        return _reject(
            "unknown_schema",
            audit={
                "schema_version": version or None,
                "expected": BRIDGE_SCHEMA_VERSION,
                "extraction_method": (payload.get("extraction") or {}).get("method"),
            },
        )
    try:
        return TrustedClinicalFactEnvelope.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — surface as reject
        return _reject(
            "schema_validation_error",
            audit={"error": str(exc), "schema_version": version},
        )


def admit_trusted_fact(
    payload: dict[str, Any] | TrustedClinicalFactEnvelope,
    *,
    clock: datetime | None = None,
) -> AdmissionDecision:
    """Gate a fact for scoring admission.

    LLM metadata never affects event-time ordering; ``clock`` is only used to
    reject future ``availability_time`` values.
    """
    if isinstance(payload, TrustedClinicalFactEnvelope):
        fact = payload
    else:
        parsed = parse_fact_payload(payload)
        if isinstance(parsed, AdmissionDecision):
            return parsed
        fact = parsed

    if fact.resource_type not in KNOWN_RESOURCE_TYPES:
        return _reject("unknown_resource_type", fact=fact)

    status = str((fact.resource or {}).get("status") or "").lower()
    if status == "cancelled" or bool((fact.extensions or {}).get("cancelled")):
        return _reject("cancelled_tombstone", fact=fact)

    if not fact.source.system or not fact.source.resource_id:
        return _reject("missing_provenance", fact=fact)

    if fact.validation.provenance != "passed":
        return _reject("missing_or_failed_provenance_check", fact=fact)

    if fact.validation.schema_status == "failed" or fact.validation.terminology == "failed":
        return _reject("failed_validation", fact=fact)

    if fact.validation.schema_status == "pending" or fact.validation.terminology == "pending":
        return _quarantine("validation_pending", fact)

    if fact.trust_status == "candidate":
        return _quarantine("candidate_not_trusted", fact)

    if fact.trust_status in {"quarantined", "rejected"}:
        return _reject(f"trust_status_{fact.trust_status}", fact=fact)

    if fact.trust_status != "trusted":
        return _reject("untrusted_status", fact=fact)

    if fact.validation.schema_status != "passed" or fact.validation.terminology != "passed":
        return _quarantine("validation_incomplete", fact)

    if fact.validation.semantic_review == "failed":
        return _reject("semantic_review_failed", fact=fact)
    if fact.validation.semantic_review == "pending":
        return _quarantine("semantic_review_pending", fact)

    # LLM-derived facts that are marked trusted still require semantic_review passed
    # or explicitly not_required (e.g. after human review promoted them).
    if fact.is_llm_derived() and fact.validation.semantic_review not in {
        "passed",
        "not_required",
    }:
        return _quarantine("llm_requires_semantic_review", fact)

    now = clock or fact.availability_time
    if fact.availability_time > now:
        return _reject("future_availability", fact=fact)

    return _admit(fact)
