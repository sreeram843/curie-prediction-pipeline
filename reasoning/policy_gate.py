"""Policy gate + quarantine path for GRP outputs."""

from __future__ import annotations

from reasoning.models import GateDecision, NarrativeDraft, ValidatedClaim


def apply_policy_gate(
    *,
    alert_id: str,
    draft: NarrativeDraft,
    validated: list[ValidatedClaim],
    fail_closed: bool = True,
) -> GateDecision:
    if draft.abstain:
        return GateDecision(
            status="abstain",
            narrative=None,
            claims=[],
            quarantine_reason=draft.abstain_reason
            or "Insufficient grounded evidence for a narrative explanation.",
            model_name=draft.model_name,
            alert_id=alert_id,
        )

    bad = [c for c in validated if not c.grounded]
    if bad:
        reasons = "; ".join(sorted({c.failure_reason or "ungrounded" for c in bad}))
        return GateDecision(
            status="quarantine",
            narrative=None,
            claims=validated,
            quarantine_reason=f"grounding_failure: {reasons}",
            model_name=draft.model_name,
            alert_id=alert_id,
        )

    if not validated and fail_closed:
        return GateDecision(
            status="abstain",
            narrative=None,
            claims=[],
            quarantine_reason="Insufficient grounded evidence for a narrative explanation.",
            model_name=draft.model_name,
            alert_id=alert_id,
        )

    claim_lines = " ".join(c.text for c in validated)
    narrative = f"{draft.summary} {claim_lines}".strip()
    return GateDecision(
        status="pass",
        narrative=narrative,
        claims=validated,
        model_name=draft.model_name,
        alert_id=alert_id,
    )
