"""Build grounded context for GRP from an already-fired alert."""

from __future__ import annotations

from typing import Any

from reasoning.models import AlertContext


def build_alert_context(alert: dict[str, Any]) -> AlertContext:
    breakdown = alert.get("component_breakdown") or []
    if breakdown and hasattr(breakdown[0], "model_dump"):
        breakdown = [c.model_dump() if hasattr(c, "model_dump") else c for c in breakdown]
    return AlertContext(
        alert_id=str(alert["alert_id"]),
        patient_id=str(alert["patient_id"]),
        score=alert.get("score"),
        tier=str(alert.get("tier") or "none"),
        completeness=str(alert.get("completeness") or "partial"),
        evidence_ids=list(alert.get("evidence_ids") or []),
        component_breakdown=list(breakdown),
        missing_components=list(alert.get("missing_components") or []),
        rule_bundle_id=str(alert.get("rule_bundle_id") or "sepsis-sofa"),
        rule_version=str(alert.get("rule_version") or "0.1.0"),
    )


def serialize_context_for_model(ctx: AlertContext) -> str:
    """Compact FHIR-ish summary — only facts already on the alert."""
    lines = [
        f"alert_id={ctx.alert_id}",
        f"patient_id={ctx.patient_id}",
        f"score={ctx.score}",
        f"tier={ctx.tier}",
        f"completeness={ctx.completeness}",
        f"rule={ctx.rule_bundle_id}@{ctx.rule_version}",
        f"evidence_ids={','.join(ctx.evidence_ids) or '(none)'}",
        f"missing_components={','.join(ctx.missing_components) or '(none)'}",
        "components:",
    ]
    for c in ctx.component_breakdown:
        name = c.get("name")
        if c.get("missing"):
            lines.append(f"  - {name}: missing")
        else:
            ev = ",".join(c.get("evidence_ids") or [])
            lines.append(f"  - {name}: points={c.get('points')} evidence={ev}")
    return "\n".join(lines)
