"""Model clients for GRP. Deterministic stub is default — never invents evidence."""

from __future__ import annotations

from reasoning.models import AlertContext, Claim, NarrativeDraft
from reasoning.openai_compat import generate_openai_compat

__all__ = [
    "generate_deterministic",
    "generate_openai_compat",
    "generate_ungrounded_hallucination",
]


def generate_deterministic(ctx: AlertContext, *, model_name: str) -> NarrativeDraft:
    """Produce a grounded narrative strictly from alert evidence IDs.

    If there is no evidence, abstain explicitly.
    """
    if not ctx.evidence_ids:
        return NarrativeDraft(
            summary="",
            claims=[],
            abstain=True,
            abstain_reason="Insufficient grounded evidence for a narrative explanation.",
            model_name=model_name,
        )

    present = [
        c
        for c in ctx.component_breakdown
        if not c.get("missing") and c.get("points") is not None and int(c.get("points") or 0) > 0
    ]
    claims: list[Claim] = []
    for c in present:
        eids = list(c.get("evidence_ids") or [])
        # Only claim with at least one evidence id
        if not eids:
            continue
        claims.append(
            Claim(
                text=(
                    f"{c.get('name')} contributed {c.get('points')} SOFA point(s) "
                    f"based on ingested evidence."
                ),
                evidence_ids=eids,
            )
        )

    if not claims:
        return NarrativeDraft(
            summary="",
            claims=[],
            abstain=True,
            abstain_reason="Insufficient grounded evidence for a narrative explanation.",
            model_name=model_name,
        )

    missing_note = ""
    if ctx.missing_components:
        missing_note = (
            f" Missing components (not imputed): {', '.join(ctx.missing_components)}."
        )

    summary = (
        f"Deterministic sepsis risk alert for {ctx.patient_id}: score {ctx.score} "
        f"({ctx.completeness}), tier {ctx.tier}, rule {ctx.rule_bundle_id}@{ctx.rule_version}."
        f"{missing_note}"
    )
    return NarrativeDraft(
        summary=summary,
        claims=claims,
        abstain=False,
        model_name=model_name,
    )


def generate_ungrounded_hallucination(ctx: AlertContext, *, model_name: str) -> NarrativeDraft:
    """Test helper: deliberately ungrounded claim (must hard-fail at validator)."""
    return NarrativeDraft(
        summary="Patient has pneumonia confirmed on CT.",
        claims=[
            Claim(
                text="CT chest shows multilobar pneumonia.",
                evidence_ids=["DiagnosticReport/ct-fake-999"],
            )
        ],
        model_name=model_name,
    )
