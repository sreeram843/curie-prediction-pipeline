"""Tests for UI benchmark summary builder."""

from __future__ import annotations

from eval.benchmarks.summary import build_benchmarks_summary


def test_benchmarks_summary_has_core_cards() -> None:
    summary = build_benchmarks_summary()
    assert summary["schema_version"] == "1.0.0"
    assert "not clinical validation" in summary["disclaimer"].lower()
    ids = {b["id"] for b in summary["benchmarks"]}
    assert "challenge-2019" in ids
    assert "investor-demo" in ids
    assert "uncertainty-band" in ids
    challenge = next(b for b in summary["benchmarks"] if b["id"] == "challenge-2019")
    assert challenge["published_holdout"]["metrics"]
    assert all(m.get("explain") for m in challenge["metrics"])
    assert any("window_m12_p6" in m["label"] for m in challenge["metrics"])
    assert any("79.5%" == m["value"] for m in challenge["metrics"])
