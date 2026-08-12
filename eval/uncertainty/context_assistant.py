"""Passive uncertainty-band context assistant (CURIE-025).

Source-grounded context and closed-set mimic hypotheses only. Never changes
routing, suppression, or escalation of deterministic alerts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.uncertainty.policy import EligibilityPolicy, default_policy, evaluate_eligibility
from reasoning.claim_validator import validate_draft
from reasoning.models import Claim, NarrativeDraft

PROMPT_VERSION = "uncertainty-context.v1"

# Closed mimic vocabulary — may only be suggested when evidence IDs support the hint.
MIMIC_HINTS: dict[str, tuple[str, ...]] = {
    "chronic_baseline": ("baseline", "chronic", "esrd"),
    "measurement_artifact": ("artifact", "hemolyzed", "spurious"),
    "already_on_pathway": ("protocol", "pathway", "treated"),
}


class ContextClaim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    grounded: bool = True
    kind: Literal["context", "conflict", "missing", "mimic", "abstain_note"] = "context"


class UncertaintyAssistResult(BaseModel):
    case_id: str
    eligible: bool
    eligibility_reasons: list[str]
    status: Literal["pass", "abstain", "quarantine", "skipped"]
    claims: list[ContextClaim] = Field(default_factory=list)
    mimics: list[str] = Field(default_factory=list)
    unsupported_claim_count: int = 0
    abstained: bool = False
    prompt_version: str = PROMPT_VERSION
    model_name: str = "curie-uncertainty-stub-v1"
    # Hard safety flags
    routing_before: str | None = None
    routing_after: str | None = None
    routing_unchanged: Literal[True] = True
    suppressed_alert: Literal[False] = False
    escalated_alert: Literal[False] = False
    interruptive_depends_on_llm: Literal[False] = False


def _allowed_evidence(case: dict[str, Any]) -> list[str]:
    ids = list(case.get("evidence_ids") or [])
    for c in case.get("component_breakdown") or []:
        if isinstance(c, dict):
            for e in c.get("evidence_ids") or []:
                if e not in ids:
                    ids.append(e)
    for s in case.get("signals") or []:
        if isinstance(s, dict):
            for e in s.get("evidence_ids") or []:
                if e not in ids:
                    ids.append(e)
    return ids


def _deterministic_context_draft(case: dict[str, Any], *, allowed: list[str]) -> NarrativeDraft:
    claims: list[Claim] = []
    if not allowed:
        return NarrativeDraft(
            summary="",
            claims=[],
            abstain=True,
            abstain_reason="No evidence IDs available for grounded uncertainty context.",
            model_name="curie-uncertainty-stub-v1",
        )

    # Context: cite first evidence for score/tier statement
    claims.append(
        Claim(
            text=(
                f"Deterministic signal {case.get('indicator') or case.get('dominant_signal_type') or 'unknown'} "
                f"at tier {case.get('tier') or case.get('dominant_severity')} "
                f"score={case.get('score')} (completeness={case.get('completeness')})."
            ),
            evidence_ids=[allowed[0]],
        )
    )

    missing = list(case.get("missing_components") or case.get("missing_inputs") or [])
    if missing:
        claims.append(
            Claim(
                text=f"Missing inputs disclosed (not imputed): {', '.join(missing)}.",
                evidence_ids=[allowed[0]],
            )
        )

    # Conflicts: positive vs missing
    positive = [
        c
        for c in (case.get("component_breakdown") or [])
        if isinstance(c, dict)
        and not c.get("missing")
        and c.get("points") is not None
        and int(c.get("points") or 0) > 0
        and c.get("evidence_ids")
    ]
    if positive and missing:
        eids = list(positive[0].get("evidence_ids") or [allowed[0]])
        claims.append(
            Claim(
                text=(
                    f"Conflict band: {positive[0].get('name')} is positive while "
                    f"{', '.join(missing)} remain missing."
                ),
                evidence_ids=eids,
            )
        )

    # Mimics: only if note/text hints AND we still cite real evidence (not inventing)
    note = str(case.get("reviewer_note") or case.get("context_note") or "").lower()
    mimic_claims: list[Claim] = []
    for mimic, hints in MIMIC_HINTS.items():
        if any(h in note for h in hints):
            mimic_claims.append(
                Claim(
                    text=f"Possible mimic to consider (passive only): {mimic}.",
                    evidence_ids=[allowed[0]],
                )
            )
    claims.extend(mimic_claims)

    return NarrativeDraft(
        summary="Uncertainty-band passive context (retrospective).",
        claims=claims,
        abstain=False,
        model_name="curie-uncertainty-stub-v1",
    )


def assist_case(
    case: dict[str, Any],
    *,
    policy: EligibilityPolicy | None = None,
    inject_ungrounded: bool = False,
) -> UncertaintyAssistResult:
    """Run passive context assist. Never mutates routing."""
    pol = policy or default_policy()
    case_id = str(case.get("case_id") or case.get("alert_id") or case.get("episode_id") or "unknown")
    routing_before = case.get("routing")
    elig = evaluate_eligibility(case, policy=pol)

    if not elig["eligible"]:
        return UncertaintyAssistResult(
            case_id=case_id,
            eligible=False,
            eligibility_reasons=list(elig["reasons"]),
            status="skipped",
            routing_before=routing_before,
            routing_after=routing_before,
        )

    allowed = _allowed_evidence(case)
    ctx = type("Ctx", (), {"evidence_ids": allowed})()

    if inject_ungrounded:
        draft = NarrativeDraft(
            summary="Ungrounded mimic",
            claims=[
                Claim(
                    text="CT proves alternative diagnosis without evidence.",
                    evidence_ids=["DiagnosticReport/fake-mimic"],
                )
            ],
            model_name="curie-uncertainty-stub-v1",
        )
    else:
        draft = _deterministic_context_draft(case, allowed=allowed)

    if draft.abstain:
        return UncertaintyAssistResult(
            case_id=case_id,
            eligible=True,
            eligibility_reasons=list(elig["reasons"]),
            status="abstain",
            abstained=True,
            claims=[
                ContextClaim(
                    text=draft.abstain_reason or "abstain",
                    evidence_ids=[],
                    grounded=False,
                    kind="abstain_note",
                )
            ],
            routing_before=routing_before,
            routing_after=routing_before,
        )

    validated = validate_draft(draft, ctx)  # type: ignore[arg-type]
    bad = [c for c in validated if not c.grounded]
    if bad:
        return UncertaintyAssistResult(
            case_id=case_id,
            eligible=True,
            eligibility_reasons=list(elig["reasons"]),
            status="quarantine",
            claims=[
                ContextClaim(
                    text=c.text,
                    evidence_ids=c.evidence_ids,
                    grounded=c.grounded,
                    kind="context",
                )
                for c in validated
            ],
            unsupported_claim_count=len(bad),
            routing_before=routing_before,
            routing_after=routing_before,
        )

    mimics = []
    out_claims: list[ContextClaim] = []
    for c in validated:
        kind: Literal["context", "conflict", "missing", "mimic", "abstain_note"] = "context"
        low = c.text.lower()
        if "missing inputs" in low:
            kind = "missing"
        elif "conflict" in low:
            kind = "conflict"
        elif "mimic" in low:
            kind = "mimic"
            # extract mimic token after colon
            if ":" in c.text:
                mimics.append(c.text.split(":", 1)[1].strip().rstrip("."))
        out_claims.append(
            ContextClaim(
                text=c.text,
                evidence_ids=c.evidence_ids,
                grounded=True,
                kind=kind,
            )
        )

    # Routing must be unchanged — assistant has no API to change it
    return UncertaintyAssistResult(
        case_id=case_id,
        eligible=True,
        eligibility_reasons=list(elig["reasons"]),
        status="pass",
        claims=out_claims,
        mimics=mimics,
        unsupported_claim_count=0,
        routing_before=routing_before,
        routing_after=routing_before,
    )
