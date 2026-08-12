"""PhysioNet Challenge 2019 official utility (pure Python port).

Source of truth: physionetchallenges/evaluation-2019 ``evaluate_sepsis_score.py``
(``compute_prediction_utility`` + cohort normalization).
"""

from __future__ import annotations

from collections.abc import Sequence


def compute_prediction_utility(
    labels: Sequence[int],
    predictions: Sequence[int],
    *,
    dt_early: int = -12,
    dt_optimal: int = -6,
    dt_late: float = 3.0,
    max_u_tp: float = 1.0,
    min_u_fn: float = -2.0,
    u_fp: float = -0.05,
    u_tn: float = 0.0,
) -> float:
    """Time-dependent utility for one stay (unnormalized sum over hours)."""
    if len(predictions) != len(labels):
        raise ValueError("Numbers of predictions and labels must be the same.")
    for label in labels:
        if label not in (0, 1):
            raise ValueError("Labels must satisfy label == 0 or label == 1.")
    for prediction in predictions:
        if prediction not in (0, 1):
            raise ValueError("Predictions must satisfy prediction == 0 or prediction == 1.")
    if dt_early >= dt_optimal:
        raise ValueError("dt_early must be before dt_optimal.")
    if dt_optimal >= dt_late:
        raise ValueError("dt_optimal must be before dt_late.")

    if any(labels):
        is_septic = True
        t_sepsis = next(i for i, y in enumerate(labels) if y) - dt_optimal
    else:
        is_septic = False
        t_sepsis = float("inf")

    m_1 = float(max_u_tp) / float(dt_optimal - dt_early)
    b_1 = -m_1 * dt_early
    m_2 = float(-max_u_tp) / float(dt_late - dt_optimal)
    b_2 = -m_2 * dt_late
    m_3 = float(min_u_fn) / float(dt_late - dt_optimal)
    b_3 = -m_3 * dt_optimal

    total = 0.0
    n = len(labels)
    for t in range(n):
        if t > t_sepsis + dt_late:
            continue
        pred = predictions[t]
        if is_septic and pred:
            if t <= t_sepsis + dt_optimal:
                total += max(m_1 * (t - t_sepsis) + b_1, u_fp)
            elif t <= t_sepsis + dt_late:
                total += m_2 * (t - t_sepsis) + b_2
        elif not is_septic and pred:
            total += u_fp
        elif is_septic and not pred:
            if t <= t_sepsis + dt_optimal:
                total += 0.0
            elif t <= t_sepsis + dt_late:
                total += m_3 * (t - t_sepsis) + b_3
        else:
            total += u_tn
    return total


def _best_predictions(
    labels: Sequence[int],
    *,
    dt_early: int = -12,
    dt_optimal: int = -6,
    dt_late: float = 3.0,
) -> list[int]:
    n = len(labels)
    best = [0] * n
    if any(labels):
        t_sepsis = next(i for i, y in enumerate(labels) if y) - dt_optimal
        start = max(0, int(t_sepsis + dt_early))
        end = min(int(t_sepsis + dt_late) + 1, n)
        for i in range(start, end):
            best[i] = 1
    return best


def normalize_cohort_utility(
    stay_labels: Sequence[Sequence[int]],
    stay_predictions: Sequence[Sequence[int]],
) -> dict[str, float]:
    """Normalized utility for a cohort (1 = optimal, 0 = no positives)."""
    if len(stay_labels) != len(stay_predictions):
        raise ValueError("Stay label/prediction counts must match.")

    observed = 0.0
    best = 0.0
    inaction = 0.0
    for labels, preds in zip(stay_labels, stay_predictions, strict=True):
        observed += compute_prediction_utility(labels, preds)
        best += compute_prediction_utility(labels, _best_predictions(labels))
        inaction += compute_prediction_utility(labels, [0] * len(labels))

    denom = best - inaction
    normalized = (observed - inaction) / denom if denom else 0.0
    return {
        "unnormalized_observed": observed,
        "unnormalized_best": best,
        "unnormalized_inaction": inaction,
        "normalized_utility": normalized,
    }


def binary_predictions_from_alert_hours(
    n_hours: int,
    alert_hours: Sequence[int] | None,
    *,
    hour_index: Sequence[int] | None = None,
) -> list[int]:
    """Map sparse alert ICULOS hours onto a length-n hourly prediction vector.

    If ``hour_index`` is provided (ICULOS per row), match by value; else treat
    ``alert_hours`` as 0-based row indices.
    """
    preds = [0] * n_hours
    if not alert_hours:
        return preds
    if hour_index is None:
        for h in alert_hours:
            if 0 <= int(h) < n_hours:
                preds[int(h)] = 1
        return preds
    wanted = {int(h) for h in alert_hours}
    for i, iculos in enumerate(hour_index):
        if int(iculos) in wanted:
            preds[i] = 1
    return preds
