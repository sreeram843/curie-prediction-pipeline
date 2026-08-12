"""Tests for Challenge 2019 detection-window robustness."""

from __future__ import annotations

from pathlib import Path

from eval.challenge2019.bootstrap import (
    detected_early_only,
    detected_in_window,
    is_detected,
    summarize_stay_metrics,
)
from eval.challenge2019.robustness import ranking_stable, run_robustness, summarize_modes
from eval.challenge2019.sweep import DEFAULT_FREEZE_PATH

FIXTURE_ROOT = Path(__file__).resolve().parent / "challenge2019"


def test_detection_mode_helpers() -> None:
    assert detected_early_only(5, 10) is True
    assert detected_early_only(10, 10) is False
    assert detected_in_window([1, 20], 10, before=12, after=12) is True
    assert detected_in_window([30], 10, before=12, after=12) is False
    row = {
        "onset_iculos": 10,
        "first_governed_iculos": 11,
        "governed_alert_hours": [11, 16],
    }
    assert is_detected(row, path="governed", mode="grace_0") is False
    assert is_detected(row, path="governed", mode="grace_6") is True
    assert is_detected(row, path="governed", mode="early_only") is False
    assert is_detected(row, path="governed", mode="window_pm12") is True


def test_summarize_modes_on_synthetic_rows() -> None:
    rows = [
        {
            "sepsis": True,
            "onset_iculos": 10,
            "naive_alert_count": 1,
            "governed_alert_count": 1,
            "watch_alert_count": 1,
            "interruptive_alert_count": 0,
            "naive_alert_hours": [8],
            "governed_alert_hours": [8],
            "interruptive_alert_hours": [],
            "first_naive_iculos": 8,
            "first_governed_iculos": 8,
            "first_interruptive_iculos": None,
        }
    ]
    modes = summarize_modes(rows)
    assert modes["grace_6"]["governed_sensitivity"] == 1.0
    assert modes["early_only"]["governed_sensitivity"] == 1.0
    g0 = summarize_stay_metrics(rows, detection_mode="grace_0")
    # first=8, onset=10 → 8 <= 10 + 0
    assert g0["detection"]["governed_sensitivity"] == 1.0


def test_ranking_stable_helper() -> None:
    ranks = {
        "window_m12_p6": ["a", "b"],
        "grace_0": ["a", "b"],
        "grace_6": ["a", "b"],
        "grace_12": ["a", "b"],
        "early_only": ["a", "b"],
        "window_pm12": ["a", "b"],
    }
    assert ranking_stable(ranks) is True
    ranks["early_only"] = ["b", "a"]
    assert ranking_stable(ranks) is False


def test_robustness_on_fixture() -> None:
    assert DEFAULT_FREEZE_PATH.is_file(), "Task 5 freeze sidecar required"
    report = run_robustness(
        root=FIXTURE_ROOT,
        set_name="training_setB",
        limit=5,
        freeze_path=DEFAULT_FREEZE_PATH,
        include_profiles=True,
        jobs=1,
    )
    assert report["stays_scored"] >= 1
    assert "frozen" in report["by_config"]
    assert "window_m12_p6" in report["by_config"]["frozen"]
    assert "grace_6" in report["by_config"]["frozen"]
    assert "ranking_by_mode" in report
