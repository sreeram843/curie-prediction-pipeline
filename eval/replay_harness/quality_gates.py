"""Deterministic page-quality / data-quality gates (CURIE-033).

Never depends on LLM availability. Failed gates downgrade interruptive → passive
with an explicit ``page_deferred_reason`` (or suppress when configured).
"""

from __future__ import annotations

from typing import Any


def quality_defer_reason(alert: dict[str, Any], *, config: Any) -> str | None:
    """Return a defer reason when the alert fails page-quality gates, else None."""
    if not getattr(config, "quality_gate_enabled", False):
        return None

    freshness = alert.get("data_age_minutes")
    max_age = int(getattr(config, "quality_max_data_age_minutes", 0) or 0)
    if max_age > 0 and freshness is not None and float(freshness) > max_age:
        return "quality_stale"

    if getattr(config, "quality_reject_invalid", True) and alert.get("invalid_observation"):
        return "quality_invalid"

    if getattr(config, "quality_reject_contradictory", True) and alert.get(
        "contradictory_observations"
    ):
        return "quality_contradictory"

    missing_critical = alert.get("missing_critical_inputs") or []
    if getattr(config, "quality_require_critical_inputs", False) and missing_critical:
        return "quality_missing_critical"

    trust = str(alert.get("source_trust") or "trusted").lower()
    if getattr(config, "quality_require_trusted_source", False) and trust != "trusted":
        return "quality_untrusted_source"

    ood = alert.get("out_of_distribution")
    if getattr(config, "quality_reject_ood", False) and ood:
        return "quality_ood"

    return None
