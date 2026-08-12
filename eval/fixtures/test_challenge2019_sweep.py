"""Tests for Challenge 2019 setA sweep / freeze / holdout selection."""

from __future__ import annotations

from pathlib import Path

from eval.challenge2019.sweep import (
    freeze_winner,
    meets_coprimary,
    meets_primary,
    rank_key,
    run_holdout,
    run_sweep,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "challenge2019"


def test_meets_primary_absolute_and_relative() -> None:
    assert meets_primary(
        {"detection": {"naive_sensitivity": 0.9, "governed_sensitivity": 0.85}}
    )
    assert meets_primary(
        {"detection": {"naive_sensitivity": 0.9, "governed_sensitivity": 0.72}}
    )
    assert not meets_primary(
        {"detection": {"naive_sensitivity": 0.9, "governed_sensitivity": 0.5}}
    )
    assert meets_primary(
        {"detection": {"naive_sensitivity": 0.9, "governed_sensitivity": 0.70}}
    )


def test_rank_prefers_primary_then_lower_burden() -> None:
    low_burden = {
        "detection": {"governed_sensitivity": 0.8, "interruptive_nna": 40},
        "alerts": {"interruptive_reduction_ratio": 0.2, "alert_reduction_ratio": 0.5},
    }
    high_burden = {
        "detection": {"governed_sensitivity": 0.85, "interruptive_nna": 40},
        "alerts": {"interruptive_reduction_ratio": 0.5, "alert_reduction_ratio": 0.5},
    }
    knobs = {"page_gate_enabled": True}
    assert rank_key(knobs, low_burden) > rank_key(knobs, high_burden)


def test_sweep_freeze_holdout_on_fixture(tmp_path: Path) -> None:
    sweep = run_sweep(
        root=FIXTURE_ROOT, limit=5, grace_hours=6, bootstrap_samples=0, jobs=1
    )
    assert sweep["stays_scored"] >= 1
    assert sweep["n_candidates"] >= 5
    assert sweep["winner_id"]
    freeze_path = tmp_path / "winner.json"
    payload = freeze_winner(sweep, freeze_path)
    assert freeze_path.is_file()
    assert "knobs" in payload
    assert "trajectory_persistence_minutes" in payload["knobs"]
    holdout = run_holdout(
        freeze_path, root=FIXTURE_ROOT, limit=5, grace_hours=6, bootstrap_samples=20
    )
    assert holdout["stays_scored"] >= 1
    assert "holdout" in holdout
    assert "meets_primary" in holdout["holdout"]
    assert meets_coprimary(
        holdout, page_gate=bool(holdout["gov_profile_meta"]["page_gate_enabled"])
    ) in (True, False)
