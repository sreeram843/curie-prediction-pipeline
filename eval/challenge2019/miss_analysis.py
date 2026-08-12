"""CURIE-030: attribute governed false negatives to a decisive cause."""

from __future__ import annotations

from collections import Counter
from typing import Any

# First decisive cause wins when multiple flags are present (order matters).
MISS_REASONS: tuple[str, ...] = (
    "missing_input",
    "scorer_threshold",
    "persistence",
    "baseline",
    "context_suppression",
    "refractory",
    "page_gate",
    "arbitration",
    "timing_window",
)

_REASON_FIELDS: dict[str, tuple[str, ...]] = {
    "missing_input": (
        "missing_input",
        "insufficient_data",
        "unscoreable",
        "zero_signal",
    ),
    "scorer_threshold": ("below_threshold", "scorer_threshold", "score_below_threshold"),
    "persistence": ("trajectory_not_met", "persistence", "min_crossings"),
    "baseline": ("baseline_block", "baseline"),
    "context_suppression": ("context_suppression", "suppressed", "comfort_care"),
    "refractory": ("refractory", "within_refractory"),
    "page_gate": ("page_gate", "page_gate_block"),
    "arbitration": ("arbitration", "episode_passive", "duplicate_signal"),
    "timing_window": ("timing_window", "outside_window", "grace_miss"),
}


def attribute_false_negative(stay_row: dict[str, Any]) -> dict[str, Any]:
    """Return ``{primary_reason, contributing}`` for one FN stay (fixture-friendly)."""
    flags = {
        str(x).lower()
        for x in (
            list(stay_row.get("suppress_reasons") or [])
            + list(stay_row.get("miss_flags") or [])
            + ([stay_row["primary_block"]] if stay_row.get("primary_block") else [])
        )
    }
    reason_text = str(stay_row.get("gov_reason") or stay_row.get("reason") or "").lower()
    if reason_text:
        flags.add(reason_text)

    matched: list[str] = []
    for reason, needles in _REASON_FIELDS.items():
        if any(n in flags or n in reason_text for n in needles):
            matched.append(reason)

    if stay_row.get("had_governed_alert") and not stay_row.get("in_window"):
        if "timing_window" not in matched:
            matched.append("timing_window")
    if stay_row.get("completeness") == "insufficient_data" or stay_row.get(
        "unscoreable"
    ):
        if "missing_input" not in matched:
            matched.insert(0, "missing_input")

    if not matched:
        matched = ["timing_window"]

    primary = matched[0]
    # Prefer earliest decisive cause in MISS_REASONS order
    for reason in MISS_REASONS:
        if reason in matched:
            primary = reason
            break
    contributing = [r for r in matched if r != primary]
    return {
        "stay_id": stay_row.get("stay_id") or stay_row.get("id"),
        "primary_reason": primary,
        "contributing": contributing,
    }


def build_miss_table(
    rows: list[dict[str, Any]],
    *,
    rule_config_hash: str | None = None,
) -> dict[str, Any]:
    attributions = [attribute_false_negative(r) for r in rows]
    counts = Counter(a["primary_reason"] for a in attributions)
    n = len(attributions) or 1
    by_reason = [
        {
            "reason": reason,
            "count": counts.get(reason, 0),
            "rate": round(counts.get(reason, 0) / n, 4),
        }
        for reason in MISS_REASONS
        if counts.get(reason, 0) > 0
    ]
    examples = []
    for a in attributions[:5]:
        examples.append(
            {
                "stay_id": a["stay_id"],
                "primary_reason": a["primary_reason"],
                "contributing": a["contributing"],
            }
        )
    return {
        "schema_version": "1.0.0",
        "n_false_negatives": len(attributions),
        "by_primary_reason": by_reason,
        "examples": examples,
        "rule_config_hash": rule_config_hash,
        "notes": [
            "Synthetic / aggregate miss attribution — no PHI.",
            "primary_reason is the first decisive cause in policy order.",
        ],
    }


def miss_table_markdown(table: dict[str, Any]) -> str:
    lines = [
        "| Reason | Count | Rate |",
        "| --- | ---: | ---: |",
    ]
    for row in table.get("by_primary_reason") or []:
        lines.append(
            f"| {row['reason']} | {row['count']} | {row['rate']:.1%} |"
        )
    return "\n".join(lines)
