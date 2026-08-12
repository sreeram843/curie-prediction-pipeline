"""CURIE-003: NNA / PPV metric definitions and edge cases."""

from __future__ import annotations

from eval.challenge2019.bootstrap import summarize_stay_metrics


def _row(
    *,
    sepsis: bool,
    onset: int | None,
    naive: int,
    governed: int,
    watch: int,
    interruptive: int,
    first_naive: int | None,
    first_gov: int | None,
    first_int: int | None,
    hours: int = 24,
) -> dict:
    return {
        "sepsis": sepsis,
        "onset_iculos": onset,
        "hours": hours,
        "naive_alert_count": naive,
        "governed_alert_count": governed,
        "watch_alert_count": watch,
        "interruptive_alert_count": interruptive,
        "first_naive_iculos": first_naive,
        "first_governed_iculos": first_gov,
        "first_interruptive_iculos": first_int,
        "naive_alert_hours": [first_naive] if first_naive is not None else [],
        "governed_alert_hours": [first_gov] if first_gov is not None else [],
        "interruptive_alert_hours": [first_int] if first_int is not None else [],
    }


def test_interruptive_nna_uses_interruptive_tp_denominator() -> None:
    """Page NNA = pages / interruptive TP, not pages / any-governed TP."""
    # Synthetic setB-scale: 41158 pages, 437 interruptive TP, 926 governed TP
    # → NNA ≈ 94.18; legacy pages/gov_tp ≈ 44.45
    rows = []
    for i in range(437):
        rows.append(
            _row(
                sepsis=True,
                onset=20,
                naive=2,
                governed=2,
                watch=1,
                interruptive=1,
                first_naive=10,
                first_gov=10,
                first_int=12,
            )
        )
    # Additional governed-only detections (watch, no page) → inflate gov_tp
    for i in range(489):
        rows.append(
            _row(
                sepsis=True,
                onset=20,
                naive=1,
                governed=1,
                watch=1,
                interruptive=0,
                first_naive=10,
                first_gov=10,
                first_int=None,
            )
        )
    # Non-sepsis with pages to pad alert totals toward 41158
    # 437 interruptive already from TP stays; need 41158 - 437 = 40721 more pages
    pages_left = 41158 - 437
    # Pack into non-sepsis stays (FP)
    while pages_left > 0:
        chunk = min(pages_left, 50)
        rows.append(
            _row(
                sepsis=False,
                onset=None,
                naive=chunk,
                governed=chunk,
                watch=0,
                interruptive=chunk,
                first_naive=1,
                first_gov=1,
                first_int=1,
            )
        )
        pages_left -= chunk

    summary = summarize_stay_metrics(rows, grace_hours=6)
    det = summary["detection"]
    details = summary["metric_details"]["nna"]

    assert det["interruptive_tp"] == 437
    assert det["governed_tp"] == 437 + 489
    assert summary["alerts"]["interruptive_total"] == 41158

    assert details["interruptive"]["numerator"] == 41158
    assert details["interruptive"]["denominator"] == 437
    assert abs(det["interruptive_nna"] - (41158 / 437)) < 1e-9
    assert abs(det["interruptive_nna"] - 94.18306636155607) < 1e-6

    # Legacy companion preserved
    assert abs(det["interruptive_nna_per_governed_tp"] - (41158 / 926)) < 1e-9
    assert details["interruptive"]["unit"] == (
        "interruptive_alerts_per_interruptive_tp_stay"
    )


def test_nna_none_when_zero_true_positives() -> None:
    rows = [
        _row(
            sepsis=True,
            onset=10,
            naive=0,
            governed=0,
            watch=0,
            interruptive=0,
            first_naive=None,
            first_gov=None,
            first_int=None,
        ),
        _row(
            sepsis=False,
            onset=None,
            naive=5,
            governed=3,
            watch=1,
            interruptive=2,
            first_naive=1,
            first_gov=1,
            first_int=1,
        ),
    ]
    summary = summarize_stay_metrics(rows, grace_hours=6)
    det = summary["detection"]
    assert det["interruptive_tp"] == 0
    assert det["governed_tp"] == 0
    assert det["interruptive_nna"] is None
    assert det["governed_nna"] is None
    assert det["interruptive_nna_per_governed_tp"] is None
    assert summary["metric_details"]["nna"]["interruptive"]["value"] is None


def test_nna_none_when_zero_alerts_but_has_tp() -> None:
    """Zero alerts → NNA value 0.0 with denom > 0 (not None)."""
    rows = [
        _row(
            sepsis=True,
            onset=10,
            naive=1,
            governed=1,
            watch=1,
            interruptive=0,
            first_naive=8,
            first_gov=8,
            first_int=None,
        ),
    ]
    summary = summarize_stay_metrics(rows, grace_hours=6)
    det = summary["detection"]
    assert det["governed_tp"] == 1
    assert det["interruptive_tp"] == 0
    assert det["governed_nna"] == 1.0
    assert det["interruptive_nna"] is None  # zero interruptive TP


def test_ppv_units_of_analysis_are_labeled() -> None:
    rows = [
        _row(
            sepsis=True,
            onset=10,
            naive=2,
            governed=2,
            watch=1,
            interruptive=1,
            first_naive=8,
            first_gov=8,
            first_int=9,
        ),
        _row(
            sepsis=False,
            onset=None,
            naive=1,
            governed=1,
            watch=0,
            interruptive=1,
            first_naive=1,
            first_gov=1,
            first_int=1,
        ),
    ]
    summary = summarize_stay_metrics(rows, grace_hours=6)
    ppv = summary["metric_details"]["ppv"]
    assert "stay_level" in ppv
    assert "event_level" in ppv
    assert ppv["episode_level"]["value"] is None
    stay = ppv["stay_level"]["interruptive"]
    assert stay["numerator"] == 1
    assert stay["denominator"] == 2
    assert stay["value"] == 0.5
    assert "stay" in stay["unit"]
    event = ppv["event_level"]["interruptive"]
    assert event["numerator"] == 1
    assert event["denominator"] == 2
