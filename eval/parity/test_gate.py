"""CURIE-007: Python side of the cross-runtime parity gate."""

from __future__ import annotations

from eval.parity.gate import count_fixtures, run_parity_gate


def test_parity_gate_zero_mismatches() -> None:
    report = run_parity_gate()
    assert report["fixture_total"] > 0
    assert report["mismatch_count"] == 0, report["mismatches"]
    assert report["ok"] is True


def test_parity_fixture_counts_are_reported() -> None:
    counts = count_fixtures()
    assert counts["sofa_cases"] >= 1
    assert counts["aki_cases"] >= 1
    assert counts["governance_decisions"] >= 1
    assert counts["governance_config_fields"] >= 1
