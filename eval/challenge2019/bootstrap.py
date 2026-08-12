"""Stay-level bootstrap confidence intervals for Challenge 2019 eval metrics."""

from __future__ import annotations

import random
from typing import Any


def detected(first_alert: int | None, onset: int | None, grace_hours: int) -> bool:
    if onset is None or first_alert is None:
        return False
    return first_alert <= onset + grace_hours


def detected_early_only(first_alert: int | None, onset: int | None) -> bool:
    """True if first alert is strictly before onset."""
    if onset is None or first_alert is None:
        return False
    return first_alert < onset


def detected_in_window(
    alert_hours: list[int] | None,
    onset: int | None,
    *,
    before: int = 12,
    after: int = 12,
) -> bool:
    """True if any alert hour falls in [onset - before, onset + after]."""
    if onset is None or not alert_hours:
        return False
    lo = onset - before
    hi = onset + after
    return any(lo <= h <= hi for h in alert_hours)


DetectionMode = str  # grace_0 | grace_6 | grace_12 | early_only | window_pm12


def is_detected(
    row: dict,
    *,
    path: str,
    mode: DetectionMode,
) -> bool:
    """path: naive | governed | interruptive."""
    onset = row.get("onset_iculos")
    first_key = {
        "naive": "first_naive_iculos",
        "governed": "first_governed_iculos",
        "interruptive": "first_interruptive_iculos",
    }[path]
    hours_key = {
        "naive": "naive_alert_hours",
        "governed": "governed_alert_hours",
        "interruptive": "interruptive_alert_hours",
    }[path]
    first = row.get(first_key)
    if mode.startswith("grace_"):
        grace = int(mode.split("_", 1)[1])
        return detected(first, onset, grace)
    if mode == "early_only":
        return detected_early_only(first, onset)
    if mode == "window_pm12":
        hours = row.get(hours_key)
        if hours is None and first is not None:
            hours = [first]
        return detected_in_window(hours, onset, before=12, after=12)
    raise ValueError(f"Unknown detection mode {mode!r}")


DETECTION_MODES: tuple[DetectionMode, ...] = (
    "grace_0",
    "grace_6",
    "grace_12",
    "early_only",
    "window_pm12",
)


def _mean(xs: list[float | int]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def ratio(
    numerator: float | int,
    denominator: float | int,
    *,
    unit: str,
) -> dict[str, Any]:
    """Ratio with explicit numerator/denominator (None value when denom is 0)."""
    num = float(numerator)
    den = float(denominator)
    return {
        "value": (num / den) if den else None,
        "numerator": num,
        "denominator": den,
        "unit": unit,
    }


def summarize_stay_metrics(
    rows: list[dict],
    grace_hours: int = 6,
    *,
    detection_mode: DetectionMode | None = None,
) -> dict[str, Any]:
    """Point estimates from a (possibly resampled) list of stay result rows.

    If ``detection_mode`` is set, it overrides ``grace_hours`` for TP / sensitivity.
    Alert totals and FP stays are mode-independent.

    NNA definitions (CURIE-003):
    - ``naive_nna`` / ``governed_nna``: alerts / path TP stays
    - ``interruptive_nna``: interruptive alerts / interruptive TP stays
    - ``interruptive_nna_per_governed_tp``: pages / any-governed TP (legacy page burden)
    """
    sepsis = [r for r in rows if r["sepsis"]]
    non = [r for r in rows if not r["sepsis"]]
    mode: DetectionMode = detection_mode or f"grace_{grace_hours}"

    naive_tp = sum(1 for r in sepsis if is_detected(r, path="naive", mode=mode))
    gov_tp = sum(1 for r in sepsis if is_detected(r, path="governed", mode=mode))
    interruptive_tp = sum(
        1 for r in sepsis if is_detected(r, path="interruptive", mode=mode)
    )
    naive_fp = sum(1 for r in non if r["naive_alert_count"] > 0)
    gov_fp = sum(1 for r in non if r["governed_alert_count"] > 0)
    interruptive_fp = sum(1 for r in non if r["interruptive_alert_count"] > 0)
    naive_alerts = sum(r["naive_alert_count"] for r in rows)
    gov_alerts = sum(r["governed_alert_count"] for r in rows)
    watch_alerts = sum(r["watch_alert_count"] for r in rows)
    interruptive_alerts = sum(r["interruptive_alert_count"] for r in rows)

    gov_alerts_on_sepsis = sum(r["governed_alert_count"] for r in sepsis)
    interruptive_alerts_on_sepsis = sum(r["interruptive_alert_count"] for r in sepsis)

    lead_naive = [
        r["onset_iculos"] - r["first_naive_iculos"]
        for r in sepsis
        if r["first_naive_iculos"] is not None and r["onset_iculos"] is not None
    ]
    lead_gov = [
        r["onset_iculos"] - r["first_governed_iculos"]
        for r in sepsis
        if r["first_governed_iculos"] is not None and r["onset_iculos"] is not None
    ]
    lead_interruptive = [
        r["onset_iculos"] - r["first_interruptive_iculos"]
        for r in sepsis
        if r["first_interruptive_iculos"] is not None and r["onset_iculos"] is not None
    ]

    n_sepsis = len(sepsis)
    patient_hours = sum(int(r.get("hours") or 0) for r in rows)
    patient_days = patient_hours / 24.0 if patient_hours else 0.0

    def _pct(xs: list[float | int], p: float) -> float | None:
        if not xs:
            return None
        s = sorted(float(x) for x in xs)
        return _percentile(s, p)

    early_gov_tp = sum(
        1 for r in sepsis if is_detected(r, path="governed", mode="early_only")
    )
    window_gov_tp = sum(
        1 for r in sepsis if is_detected(r, path="governed", mode="window_pm12")
    )

    naive_nna = ratio(
        naive_alerts,
        naive_tp,
        unit="alerts_per_detected_sepsis_stay",
    )
    governed_nna = ratio(
        gov_alerts,
        gov_tp,
        unit="alerts_per_detected_sepsis_stay",
    )
    # Primary page NNA: pages per interruptive true-positive stay
    interruptive_nna = ratio(
        interruptive_alerts,
        interruptive_tp,
        unit="interruptive_alerts_per_interruptive_tp_stay",
    )
    # Legacy companion: pages per any-governed TP (previously mislabeled interruptive_nna)
    interruptive_nna_per_governed_tp = ratio(
        interruptive_alerts,
        gov_tp,
        unit="interruptive_alerts_per_governed_tp_stay",
    )

    stay_ppv_governed = ratio(
        gov_tp,
        gov_tp + gov_fp,
        unit="detected_sepsis_stays_per_stay_with_governed_alert",
    )
    stay_ppv_interruptive = ratio(
        interruptive_tp,
        interruptive_tp + interruptive_fp,
        unit="interruptive_tp_stays_per_stay_with_interruptive_alert",
    )
    # Crude event-level: fraction of alerts that occurred on sepsis stays
    event_ppv_governed = ratio(
        gov_alerts_on_sepsis,
        gov_alerts,
        unit="governed_alerts_on_sepsis_stays_per_all_governed_alerts",
    )
    event_ppv_interruptive = ratio(
        interruptive_alerts_on_sepsis,
        interruptive_alerts,
        unit="interruptive_alerts_on_sepsis_stays_per_all_interruptive_alerts",
    )

    return {
        "detection_mode": mode,
        "cohort": {
            "sepsis_stays": n_sepsis,
            "non_sepsis_stays": len(non),
            "stays_scored": len(rows),
            "patient_hours": patient_hours,
            "patient_days": patient_days,
        },
        "alerts": {
            "naive_total": naive_alerts,
            "governed_total": gov_alerts,
            "watch_total": watch_alerts,
            "interruptive_total": interruptive_alerts,
            "alert_reduction_ratio": (gov_alerts / naive_alerts) if naive_alerts else 0.0,
            "interruptive_reduction_ratio": (
                (interruptive_alerts / naive_alerts) if naive_alerts else 0.0
            ),
            "governed_alerts_per_patient_day": (
                (gov_alerts / patient_days) if patient_days else None
            ),
            "interruptive_alerts_per_patient_day": (
                (interruptive_alerts / patient_days) if patient_days else None
            ),
        },
        "detection": {
            "naive_tp": naive_tp,
            "governed_tp": gov_tp,
            "interruptive_tp": interruptive_tp,
            "naive_sensitivity": (naive_tp / n_sepsis) if n_sepsis else None,
            "governed_sensitivity": (gov_tp / n_sepsis) if n_sepsis else None,
            "interruptive_sensitivity": (
                (interruptive_tp / n_sepsis) if n_sepsis else None
            ),
            "early_only_governed_tp": early_gov_tp,
            "early_only_governed_sensitivity": (
                (early_gov_tp / n_sepsis) if n_sepsis else None
            ),
            "window_pm12_governed_tp": window_gov_tp,
            "window_pm12_governed_sensitivity": (
                (window_gov_tp / n_sepsis) if n_sepsis else None
            ),
            "naive_fp_non_sepsis": naive_fp,
            "governed_fp_non_sepsis": gov_fp,
            "interruptive_fp_non_sepsis": interruptive_fp,
            # Flat scalars for bootstrap / sweep (values only)
            "governed_ppv_stay": stay_ppv_governed["value"],
            "interruptive_ppv_stay": stay_ppv_interruptive["value"],
            "naive_nna": naive_nna["value"],
            "governed_nna": governed_nna["value"],
            "interruptive_nna": interruptive_nna["value"],
            "interruptive_nna_per_governed_tp": interruptive_nna_per_governed_tp[
                "value"
            ],
            "mean_lead_hours_naive": _mean(lead_naive),
            "mean_lead_hours_governed": _mean(lead_gov),
            "mean_lead_hours_interruptive": _mean(lead_interruptive),
            "lead_hours_governed_p25": _pct(lead_gov, 0.25),
            "lead_hours_governed_p50": _pct(lead_gov, 0.50),
            "lead_hours_governed_p75": _pct(lead_gov, 0.75),
        },
        "metric_details": {
            "nna": {
                "naive": naive_nna,
                "governed": governed_nna,
                "interruptive": interruptive_nna,
                "interruptive_per_governed_tp": interruptive_nna_per_governed_tp,
            },
            "ppv": {
                "stay_level": {
                    "governed": stay_ppv_governed,
                    "interruptive": stay_ppv_interruptive,
                },
                "event_level": {
                    "governed": event_ppv_governed,
                    "interruptive": event_ppv_interruptive,
                    "note": (
                        "Crude: alerts on sepsis stays / all alerts; not timed to onset."
                    ),
                },
                "episode_level": {
                    "value": None,
                    "note": "Requires episode aggregation (CURIE-012).",
                },
            },
        },
    }


# Flat keys harvested from each bootstrap replicate for percentile CIs.
_BOOTSTRAP_METRICS: tuple[tuple[str, str], ...] = (
    ("detection", "naive_sensitivity"),
    ("detection", "governed_sensitivity"),
    ("detection", "interruptive_sensitivity"),
    ("detection", "governed_nna"),
    ("detection", "interruptive_nna"),
    ("detection", "interruptive_nna_per_governed_tp"),
    ("detection", "governed_ppv_stay"),
    ("detection", "interruptive_ppv_stay"),
    ("detection", "mean_lead_hours_governed"),
    ("alerts", "alert_reduction_ratio"),
    ("alerts", "interruptive_reduction_ratio"),
)


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Linear interpolation percentile; ``p`` in [0, 1]."""
    if not sorted_vals:
        raise ValueError("empty sample")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def bootstrap_metric_cis(
    rows: list[dict],
    grace_hours: int,
    *,
    n_boot: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Stay-level nonparametric bootstrap (resample with replacement).

    Replays are not re-run — only already-scored stay rows are resampled, so this
    is cheap relative to scoring.
    """
    if n_boot <= 0:
        return {}
    if not rows:
        return {
            "n_boot": n_boot,
            "seed": seed,
            "alpha": alpha,
            "method": "percentile",
            "metrics": {},
        }

    rng = random.Random(seed)
    n = len(rows)
    buckets: dict[str, list[float]] = {
        f"{section}.{key}": [] for section, key in _BOOTSTRAP_METRICS
    }

    for _ in range(n_boot):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        summary = summarize_stay_metrics(sample, grace_hours)
        for section, key in _BOOTSTRAP_METRICS:
            val = summary[section].get(key)
            if val is None:
                continue
            buckets[f"{section}.{key}"].append(float(val))

    lo_p = alpha / 2.0
    hi_p = 1.0 - alpha / 2.0
    metrics: dict[str, Any] = {}
    for name, vals in buckets.items():
        if not vals:
            metrics[name] = None
            continue
        vals_sorted = sorted(vals)
        metrics[name] = {
            "low": _percentile(vals_sorted, lo_p),
            "high": _percentile(vals_sorted, hi_p),
            "mean": sum(vals_sorted) / len(vals_sorted),
            "n": len(vals_sorted),
        }

    return {
        "n_boot": n_boot,
        "seed": seed,
        "alpha": alpha,
        "method": "percentile",
        "unit": "stay",
        "metrics": metrics,
    }
