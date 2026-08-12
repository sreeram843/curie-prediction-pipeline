"""Tests for CURIE-030 miss attribution."""

from __future__ import annotations

from eval.challenge2019.miss_analysis import (
    attribute_false_negative,
    build_miss_table,
    miss_table_markdown,
)


def test_attribute_missing_input_wins() -> None:
    got = attribute_false_negative(
        {
            "stay_id": "s1",
            "completeness": "insufficient_data",
            "gov_reason": "trajectory_not_met",
        }
    )
    assert got["primary_reason"] == "missing_input"
    assert "persistence" in got["contributing"]


def test_attribute_page_gate() -> None:
    got = attribute_false_negative(
        {"stay_id": "s2", "miss_flags": ["page_gate_block"]}
    )
    assert got["primary_reason"] == "page_gate"


def test_timing_window_when_alert_outside_window() -> None:
    got = attribute_false_negative(
        {"stay_id": "s3", "had_governed_alert": True, "in_window": False}
    )
    assert got["primary_reason"] == "timing_window"


def test_build_miss_table_and_markdown() -> None:
    rows = [
        {"stay_id": "a", "miss_flags": ["below_threshold"]},
        {"stay_id": "b", "miss_flags": ["refractory"]},
        {"stay_id": "c", "unscoreable": True},
    ]
    table = build_miss_table(rows, rule_config_hash="deadbeef")
    assert table["n_false_negatives"] == 3
    assert table["rule_config_hash"] == "deadbeef"
    reasons = {r["reason"] for r in table["by_primary_reason"]}
    assert "scorer_threshold" in reasons
    assert "refractory" in reasons
    assert "missing_input" in reasons
    md = miss_table_markdown(table)
    assert "scorer_threshold" in md
