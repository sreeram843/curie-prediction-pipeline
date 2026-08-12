"""CURIE-004: bounded primary detection window + timing classes."""

from __future__ import annotations

from eval.challenge2019.bootstrap import (
    PRIMARY_DETECTION_MODE,
    classify_timing,
    detected_in_window,
    is_detected,
    load_timing_freeze,
    summarize_stay_metrics,
)


def _row(
    *,
    sepsis: bool,
    onset: int | None,
    gov_hours: list[int],
    naive_hours: list[int] | None = None,
) -> dict:
    naive_hours = naive_hours if naive_hours is not None else gov_hours
    first_gov = min(gov_hours) if gov_hours else None
    first_naive = min(naive_hours) if naive_hours else None
    return {
        "sepsis": sepsis,
        "onset_iculos": onset,
        "hours": 48,
        "naive_alert_count": len(naive_hours),
        "governed_alert_count": len(gov_hours),
        "watch_alert_count": len(gov_hours),
        "interruptive_alert_count": 0,
        "first_naive_iculos": first_naive,
        "first_governed_iculos": first_gov,
        "first_interruptive_iculos": None,
        "naive_alert_hours": list(naive_hours),
        "governed_alert_hours": list(gov_hours),
        "interruptive_alert_hours": [],
    }


def test_timing_freeze_matches_primary_constants() -> None:
    freeze = load_timing_freeze()
    assert freeze["timing_id"] == "challenge2019-label-window-m12-p6.v1"
    assert freeze["primary_detection"]["detection_mode_id"] == PRIMARY_DETECTION_MODE
    assert "six hours" in freeze["label_semantics"]["note"].lower() or "6h" in freeze[
        "label_semantics"
    ]["note"]


def test_primary_window_rejects_unbounded_early_alert() -> None:
    """Alert 40h before label_start is TP under grace_6 but not under primary window."""
    # onset=50 → window [38, 56]; alert at hour 5 is too early
    row = _row(sepsis=True, onset=50, gov_hours=[5])
    assert is_detected(row, path="governed", mode="grace_6") is True
    assert is_detected(row, path="governed", mode=PRIMARY_DETECTION_MODE) is False
    assert classify_timing([5], 50) == "too_early"


def test_primary_window_counts_any_alert_in_window() -> None:
    # First alert too early, second in window → primary TP
    row = _row(sepsis=True, onset=50, gov_hours=[5, 45])
    assert is_detected(row, path="governed", mode=PRIMARY_DETECTION_MODE) is True
    assert classify_timing([5, 45], 50) == "in_window"


def test_timing_classes_late_and_missed() -> None:
    assert classify_timing([60], 50) == "late"  # window ends 56
    assert classify_timing([], 50) == "missed"
    assert classify_timing([5, 60], 50) == "outside_window"


def test_default_summary_uses_primary_window_not_grace() -> None:
    rows = [
        _row(sepsis=True, onset=50, gov_hours=[5]),  # grace TP, window miss
        _row(sepsis=True, onset=50, gov_hours=[45]),  # both TP
        _row(sepsis=False, onset=None, gov_hours=[1]),
    ]
    summary = summarize_stay_metrics(rows, grace_hours=6)
    assert summary["detection_mode"] == PRIMARY_DETECTION_MODE
    assert summary["detection"]["governed_tp"] == 1
    assert summary["timing"]["legacy_grace_governed_tp"] == 2
    assert summary["timing"]["governed_classes"]["too_early"] == 1
    assert summary["timing"]["governed_classes"]["in_window"] == 1
    assert "label_start" in summary["timing"]["label_start_note"]


def test_in_window_lead_ignores_prewindow_alert() -> None:
    rows = [_row(sepsis=True, onset=50, gov_hours=[5, 45])]
    summary = summarize_stay_metrics(rows)
    # Legacy lead uses first alert (50-5=45); primary uses first in window (50-45=5)
    assert summary["detection"]["mean_lead_hours_governed"] == 45
    assert summary["detection"]["mean_lead_hours_governed_in_window"] == 5


def test_detected_in_window_boundaries() -> None:
    assert detected_in_window([38], 50, before=12, after=6) is True
    assert detected_in_window([56], 50, before=12, after=6) is True
    assert detected_in_window([37], 50, before=12, after=6) is False
    assert detected_in_window([57], 50, before=12, after=6) is False
