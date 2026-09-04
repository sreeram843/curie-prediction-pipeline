"""CURIE-030: attribute governed false negatives to a decisive cause."""

from __future__ import annotations

from collections import Counter
from typing import Any

from eval.challenge2019.bootstrap import PRIMARY_DETECTION_MODE, is_detected

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
            "Aggregate miss attribution — no PHI.",
            "primary_reason is the first decisive cause in policy order.",
        ],
    }


def attribute_replay_false_negative(row: dict[str, Any]) -> dict[str, Any] | None:
    """Attribute a governed in-window miss from a Challenge replay row.

    Returns None if the stay is not a primary-window governed false negative.
    Stay identifiers are not copied into the return value.
    """
    if not row.get("sepsis"):
        return None
    if is_detected(row, path="governed", mode=PRIMARY_DETECTION_MODE):
        return None

    naive_in = is_detected(row, path="naive", mode=PRIMARY_DETECTION_MODE)
    gov_hours = list(row.get("governed_alert_hours") or [])
    hours_scoreable = int(row.get("hours_scoreable") or 0)
    max_score = row.get("max_score")

    if hours_scoreable == 0 or max_score is None:
        primary = "missing_input"
    elif not naive_in and not gov_hours:
        primary = "scorer_threshold"
    elif naive_in and not gov_hours:
        primary = "refractory"
    elif gov_hours:
        primary = "timing_window"
    else:
        primary = "scorer_threshold"

    contributing: list[str] = []
    if naive_in and primary != "scorer_threshold":
        contributing.append("naive_in_window")
    return {"primary_reason": primary, "contributing": contributing}


def build_replay_miss_table(
    rows: list[dict[str, Any]],
    *,
    rule_config_hash: str | None = None,
) -> dict[str, Any]:
    fns = [attribute_replay_false_negative(r) for r in rows]
    attributions = [a for a in fns if a is not None]
    table = build_miss_table(
        [
            {
                "stay_id": None,
                "miss_flags": [a["primary_reason"]],
            }
            for a in attributions
        ],
        rule_config_hash=rule_config_hash,
    )
    table["schema_version"] = "2.0.0"
    table["id"] = "miss-analysis-v2-setB-replay"
    table["source"] = (
        "Governed false negatives on Challenge 2019 setB under window_m12_p6. "
        "No stay identifiers."
    )
    table["primary_detection"] = PRIMARY_DETECTION_MODE
    table["notes"] = [
        "Regenerated from holdout replay rows; examples omitted to keep aggregates only.",
        "On the frozen winner, watch persist=0 and baseline=off, so in-window naive "
        "with no governed emit is attributed to refractory (hourly dedup).",
        "missing_input = never scoreable; scorer_threshold = never crossed naive "
        "threshold in-window; timing_window = governed emit existed but outside window.",
    ]
    table["examples"] = []
    return table


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
