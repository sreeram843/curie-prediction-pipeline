"""Claim validator — every claim must trace to allowed evidence IDs."""

from __future__ import annotations

from typing import Protocol

from reasoning.models import NarrativeDraft, ValidatedClaim

FORBIDDEN_PATTERNS = (
    "start antibiotics",
    "administer",
    "prescribe",
    "intubate",
    "give fluids",
    "treatment recommendation",
)

# Prompt-injection markers that must never become clinical claims.
INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "disregard grounding",
    "you are now",
)


class EvidenceContext(Protocol):
    evidence_ids: list[str]


def validate_draft(draft: NarrativeDraft, ctx: EvidenceContext) -> list[ValidatedClaim]:
    allowed = set(ctx.evidence_ids)
    validated: list[ValidatedClaim] = []
    for claim in draft.claims:
        text_l = claim.text.lower()
        if any(p in text_l for p in FORBIDDEN_PATTERNS):
            validated.append(
                ValidatedClaim(
                    text=claim.text,
                    evidence_ids=claim.evidence_ids,
                    grounded=False,
                    failure_reason="policy:treatment_instruction",
                )
            )
            continue
        if any(p in text_l for p in INJECTION_PATTERNS):
            validated.append(
                ValidatedClaim(
                    text=claim.text,
                    evidence_ids=claim.evidence_ids,
                    grounded=False,
                    failure_reason="policy:prompt_injection",
                )
            )
            continue
        if not claim.evidence_ids:
            validated.append(
                ValidatedClaim(
                    text=claim.text,
                    evidence_ids=[],
                    grounded=False,
                    failure_reason="missing_evidence_ids",
                )
            )
            continue
        unknown = [e for e in claim.evidence_ids if e not in allowed]
        if unknown:
            validated.append(
                ValidatedClaim(
                    text=claim.text,
                    evidence_ids=claim.evidence_ids,
                    grounded=False,
                    failure_reason=f"ungrounded_evidence:{','.join(unknown)}",
                )
            )
            continue
        validated.append(
            ValidatedClaim(
                text=claim.text,
                evidence_ids=claim.evidence_ids,
                grounded=True,
            )
        )
    return validated
