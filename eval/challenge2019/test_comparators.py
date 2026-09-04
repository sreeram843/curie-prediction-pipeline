"""Comparator stay replay on in-memory Challenge hours."""

from __future__ import annotations

from eval.challenge2019.comparators import replay_bedside_stay, run_comparators
from ingestion.adapters.challenge2019.loader import ChallengeHour


def _h(iculos: int, *, label: int = 0, **raw: str) -> ChallengeHour:
    return ChallengeHour(
        stay_id="p1",
        iculos=iculos,
        sepsis_label=label,
        inputs=[],
        raw=raw,
    )


def test_sirs_emits_when_two_criteria_persist() -> None:
    hours = [
        _h(1, HR="110", Temp="39.0"),
        _h(2, HR="110", Temp="39.0", SepsisLabel="1"),
    ]
    # ChallengeHour stores sepsis_label separately; raw SepsisLabel unused by replay
    hours[1].sepsis_label = 1
    row = replay_bedside_stay(hours, "sirs")
    assert row["naive_alert_hours"] == [1, 2]
    assert row["sepsis"] is True


def test_qsofa_silent_without_both_limbs() -> None:
    hours = [_h(1, Resp="24", SBP="120")]
    row = replay_bedside_stay(hours, "qsofa")
    assert row["naive_alert_hours"] == []


def test_run_comparators_cards() -> None:
    hours = [[_h(1, HR="70", Temp="37", Resp="16", WBC="8", SBP="120", O2Sat="98")]]
    report = run_comparators(hours)
    ids = {c["id"] for c in report["comparators"]}
    assert ids == {"sirs", "news2", "qsofa"}
    assert all(c["metrics"]["emissions"] == 0 for c in report["comparators"])
