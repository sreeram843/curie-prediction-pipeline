"""Unit tests for Challenge 2019 bedside comparators (no archive required)."""

from __future__ import annotations

from eval.challenge2019.bedside import (
    hour_alerts,
    news2_score,
    qsofa_score,
    sirs_criteria,
    update_vitals,
)


def test_sirs_two_criteria_alerts() -> None:
    n, flags = sirs_criteria({"Temp": 39.0, "HR": 110.0, "Resp": 16.0, "WBC": 8.0})
    assert n == 2
    assert flags["temp"] and flags["hr"]
    assert hour_alerts({"Temp": 39.0, "HR": 110.0, "Resp": 16.0, "WBC": 8.0})["sirs_alert"]


def test_sirs_missing_limb_does_not_count() -> None:
    n, flags = sirs_criteria({"Temp": None, "HR": 50.0, "Resp": 12.0, "WBC": 7.0})
    assert n == 0
    assert flags["temp"] is False


def test_news2_normal_is_zero() -> None:
    total, _ = news2_score(
        {"Resp": 16.0, "O2Sat": 98.0, "FiO2": 0.21, "Temp": 37.0, "SBP": 120.0, "HR": 70.0}
    )
    assert total == 0


def test_news2_medium_trigger() -> None:
    # RR 25 → 3, HR 131 → 3  => 6 ≥ 5
    vitals = {
        "Resp": 25.0,
        "O2Sat": 98.0,
        "FiO2": None,
        "Temp": 37.0,
        "SBP": 120.0,
        "HR": 131.0,
    }
    total, _ = news2_score(vitals)
    assert total == 6
    assert hour_alerts(vitals)["news2_alert"]
    assert hour_alerts(vitals)["news2_high_alert"] is False


def test_news2_oxygen_adds_two() -> None:
    total_air, _ = news2_score(
        {"Resp": 16.0, "O2Sat": 98.0, "FiO2": 0.21, "Temp": 37.0, "SBP": 120.0, "HR": 70.0}
    )
    total_o2, _ = news2_score(
        {"Resp": 16.0, "O2Sat": 98.0, "FiO2": 0.40, "Temp": 37.0, "SBP": 120.0, "HR": 70.0}
    )
    assert total_air == 0
    assert total_o2 == 2


def test_qsofa_needs_both_limbs_without_gcs() -> None:
    n_one, _ = qsofa_score({"Resp": 24.0, "SBP": 120.0})
    n_two, flags = qsofa_score({"Resp": 24.0, "SBP": 90.0})
    assert n_one == 1
    assert n_two == 2
    assert flags["mentation"] is False
    assert hour_alerts({"Resp": 24.0, "SBP": 90.0})["qsofa_alert"]
    assert hour_alerts({"Resp": 24.0, "SBP": 120.0})["qsofa_alert"] is False


def test_forward_fill_keeps_last_vital() -> None:
    empty = {c: None for c in ("Temp", "HR", "Resp", "WBC", "SBP", "O2Sat", "FiO2")}
    state: dict[str, float | None] = dict(empty)
    state = update_vitals(state, {"HR": "88"})
    state = update_vitals(state, {"HR": "NaN", "Temp": "38.5"})
    assert state["HR"] == 88.0
    assert state["Temp"] == 38.5
