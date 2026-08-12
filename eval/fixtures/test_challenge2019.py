"""Unit tests for Challenge 2019 loader + eval (fixture PSV, no full archive)."""

from __future__ import annotations

from pathlib import Path

from eval.challenge2019.bootstrap import bootstrap_metric_cis, summarize_stay_metrics
from eval.challenge2019.runner import run_challenge2019_eval
from ingestion.adapters.challenge2019.loader import (
    load_stay_hours,
    sepsis_onset_iculos,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "challenge2019"


def test_load_stay_forward_fills_and_onset() -> None:
    hours = load_stay_hours(FIXTURE_DIR / "p_sepsis_tiny.psv")
    assert len(hours) == 3
    assert sepsis_onset_iculos(hours) == 3
    # hour 3 should still have MAP from forward-fill / updates
    names = {i.name.value for i in hours[-1].inputs}
    assert "cardiovascular" in names
    assert "renal" in names


def test_eval_on_fixture_dir() -> None:
    report = run_challenge2019_eval(
        root=FIXTURE_DIR,
        limit=10,
        set_name="training_setA",
        detection_grace_hours=6,
        gov_profile="accuracy",
        bootstrap_samples=50,
    )
    assert report["stays_scored"] == 1
    assert report["cohort"]["sepsis_stays"] == 1
    assert report["gov_profile"] == "accuracy"
    assert "alerts" in report
    assert "detection" in report
    assert "watch_total" in report["alerts"]
    assert "interruptive_total" in report["alerts"]
    assert "interruptive_reduction_ratio" in report["alerts"]
    assert "interruptive_nna" in report["detection"]
    assert "interruptive_sensitivity" in report["detection"]
    # Dual-tier partition: watch + interruptive == governed (routing none should not emit)
    assert (
        report["alerts"]["watch_total"] + report["alerts"]["interruptive_total"]
        == report["alerts"]["governed_total"]
    )
    assert report["bootstrap"]["n_boot"] == 50
    assert "detection.governed_sensitivity" in report["bootstrap"]["metrics"]


def test_dual_profile_enables_page_gate() -> None:
    report = run_challenge2019_eval(
        root=FIXTURE_DIR,
        limit=10,
        set_name="training_setA",
        gov_profile="dual",
        bootstrap_samples=0,
    )
    assert report["gov_profile"] == "dual"
    assert report["gov_profile_meta"]["page_gate_enabled"] is True
    assert (
        report["alerts"]["watch_total"] + report["alerts"]["interruptive_total"]
        == report["alerts"]["governed_total"]
    )
    assert report["bootstrap"] == {}


def test_accuracy_profile_emits_more_than_strict() -> None:
    strict = run_challenge2019_eval(
        root=FIXTURE_DIR,
        limit=10,
        set_name="training_setA",
        gov_profile="strict",
        bootstrap_samples=0,
    )
    accuracy = run_challenge2019_eval(
        root=FIXTURE_DIR,
        limit=10,
        set_name="training_setA",
        gov_profile="accuracy",
        bootstrap_samples=0,
    )
    assert accuracy["alerts"]["governed_total"] >= strict["alerts"]["governed_total"]


def test_bootstrap_ci_bounds_bracket_point_estimate() -> None:
    rows = [
        {
            "sepsis": True,
            "onset_iculos": 10,
            "naive_alert_count": 2,
            "governed_alert_count": 1,
            "watch_alert_count": 1,
            "interruptive_alert_count": 0,
            "first_naive_iculos": 8,
            "first_governed_iculos": 8,
            "first_interruptive_iculos": None,
        },
        {
            "sepsis": True,
            "onset_iculos": 12,
            "naive_alert_count": 3,
            "governed_alert_count": 2,
            "watch_alert_count": 1,
            "interruptive_alert_count": 1,
            "first_naive_iculos": 9,
            "first_governed_iculos": 9,
            "first_interruptive_iculos": 11,
        },
        {
            "sepsis": False,
            "onset_iculos": None,
            "naive_alert_count": 1,
            "governed_alert_count": 1,
            "watch_alert_count": 1,
            "interruptive_alert_count": 0,
            "first_naive_iculos": 1,
            "first_governed_iculos": 1,
            "first_interruptive_iculos": None,
        },
        {
            "sepsis": False,
            "onset_iculos": None,
            "naive_alert_count": 0,
            "governed_alert_count": 0,
            "watch_alert_count": 0,
            "interruptive_alert_count": 0,
            "first_naive_iculos": None,
            "first_governed_iculos": None,
            "first_interruptive_iculos": None,
        },
    ]
    point = summarize_stay_metrics(rows, grace_hours=6)
    cis = bootstrap_metric_cis(rows, grace_hours=6, n_boot=200, seed=7)
    sens = point["detection"]["governed_sensitivity"]
    band = cis["metrics"]["detection.governed_sensitivity"]
    assert band is not None
    assert band["low"] <= sens <= band["high"]
    assert band["low"] <= band["high"]
