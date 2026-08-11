"""Claim validator — every claim must trace to ingested evidence IDs on the alert."""

from __future__ import annotations

from reasoning.models import AlertContext, NarrativeDraft, ValidatedClaim

FORBIDDEN_PATTERNS = (
    "start antibiotics",
    "administer",
    "prescribe",
    "intubate",
    "give fluids",
    "treatment recommendation",
)


def validate_draft(draft: NarrativeDraft, ctx: AlertContext) -> list[ValidatedClaim]:
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
