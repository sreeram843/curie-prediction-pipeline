"""Unit tests for Challenge 2019 utility (matches official evaluate_sepsis_score)."""

from eval.challenge2019.utility import (
    binary_predictions_from_alert_hours,
    compute_prediction_utility,
    normalize_cohort_utility,
)


def test_official_example_utility() -> None:
    # From evaluate_sepsis_score.py docstring example
    labels = [0, 0, 0, 0, 1, 1]
    predictions = [0, 0, 1, 1, 1, 1]
    utility = compute_prediction_utility(labels, predictions)
    assert abs(utility - 3.388888888888889) < 1e-9


def test_inaction_utility_zero_for_nonsepsis() -> None:
    labels = [0, 0, 0, 0]
    assert compute_prediction_utility(labels, [0, 0, 0, 0]) == 0.0


def test_normalize_optimal_is_one() -> None:
    labels = [[0, 0, 0, 0, 1, 1, 1, 1, 1, 1]]
    # Optimal positives: from t_sepsis+dt_early through t_sepsis+dt_late
    # first label at index 4 → t_sepsis = 4 - (-6) = 10 ... wait
    # Official: t_sepsis = argmax(labels) - dt_optimal
    # argmax of [0,0,0,0,1,1...] = 4; dt_optimal=-6 → t_sepsis = 4 - (-6) = 10
    # But len=10, so window may be empty at end — use longer stay
    labels = [[0] * 20]
    labels[0][12] = 1  # first positive at t=12 → t_sepsis = 12 - (-6) = 18
    # Window [18-12=6, 18+3=21) clipped to [6, 20)
    best = [0] * 20
    for i in range(6, 20):
        best[i] = 1
    out = normalize_cohort_utility(labels, [best])
    assert abs(out["normalized_utility"] - 1.0) < 1e-9


def test_normalize_inaction_is_zero() -> None:
    labels = [[0] * 10 + [1] + [0] * 5]
    preds = [[0] * len(labels[0])]
    out = normalize_cohort_utility(labels, preds)
    assert abs(out["normalized_utility"]) < 1e-12


def test_binary_predictions_from_iculos() -> None:
    preds = binary_predictions_from_alert_hours(
        5, [12, 14], hour_index=[10, 11, 12, 13, 14]
    )
    assert preds == [0, 0, 1, 0, 1]
