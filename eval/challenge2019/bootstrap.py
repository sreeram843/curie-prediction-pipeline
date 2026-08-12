"""Stay-level bootstrap confidence intervals for Challenge 2019 eval metrics."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Literal

TIMING_FREEZE_PATH = (
    Path(__file__).resolve().parent / "frozen" / "timing_primary.v1.json"
)

# Primary Curie detection (CURIE-004): any alert in [label_start−12h, label_start+6h].
PRIMARY_WINDOW_BEFORE = 12
PRIMARY_WINDOW_AFTER = 6
PRIMARY_DETECTION_MODE = "window_m12_p6"

TimingClass = Literal[
    "in_window", "too_early", "late", "outside_window", "missed", "non_sepsis"
]


def load_timing_freeze(path: Path | None = None) -> dict[str, Any]:
    data = json.loads((path or TIMING_FREEZE_PATH).read_text())
    primary = data["primary_detection"]
    assert primary["before_hours"] == PRIMARY_WINDOW_BEFORE
    assert primary["after_hours"] == PRIMARY_WINDOW_AFTER
    assert primary["detection_mode_id"] == PRIMARY_DETECTION_MODE
    return data


def detected(first_alert: int | None, onset: int | None, grace_hours: int) -> bool:
    """Legacy: first alert at/before onset + grace (unbounded early lead)."""
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


def classify_timing(
    alert_hours: list[int] | None,
    onset: int | None,
    *,
    before: int = PRIMARY_WINDOW_BEFORE,
    after: int = PRIMARY_WINDOW_AFTER,
) -> TimingClass:
    """Mutually exclusive timing class relative to the primary window."""
    if onset is None:
        return "non_sepsis"
    hours = [int(h) for h in (alert_hours or [])]
    lo = onset - before
    hi = onset + after
    if any(lo <= h <= hi for h in hours):
        return "in_window"
    if not hours:
        return "missed"
    if max(hours) < lo:
        return "too_early"
    if min(hours) > hi:
        return "late"
    return "outside_window"


def first_alert_in_window(
    alert_hours: list[int] | None,
    onset: int | None,
    *,
    before: int = PRIMARY_WINDOW_BEFORE,
    after: int = PRIMARY_WINDOW_AFTER,
) -> int | None:
    if onset is None or not alert_hours:
        return None
    lo = onset - before
    hi = onset + after
    in_win = sorted(h for h in alert_hours if lo <= h <= hi)
    return in_win[0] if in_win else None


def parse_window_mode(mode: str) -> tuple[int, int] | None:
    """Parse ``window_m{before}_p{after}`` or ``window_pm12`` → (before, after)."""
    if mode == "window_pm12":
        return 12, 12
    if mode.startswith("window_m") and "_p" in mode:
        # window_m12_p6
        body = mode[len("window_m") :]
        left, right = body.split("_p", 1)
        return int(left), int(right)
    return None


DetectionMode = str  # grace_* | early_only | window_*


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
    window = parse_window_mode(mode)
    if window is not None:
        before, after = window
        hours = row.get(hours_key)
        if hours is None and first is not None:
            hours = [first]
        return detected_in_window(hours, onset, before=before, after=after)
    raise ValueError(f"Unknown detection mode {mode!r}")


DETECTION_MODES: tuple[DetectionMode, ...] = (
    PRIMARY_DETECTION_MODE,
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
    window_before: int = PRIMARY_WINDOW_BEFORE,
    window_after: int = PRIMARY_WINDOW_AFTER,
) -> dict[str, Any]:
    """Point estimates from a (possibly resampled) list of stay result rows.

    Primary detection (CURIE-004) defaults to any alert in
    ``[onset - window_before, onset + window_after]`` (frozen
    ``window_m12_p6``). Legacy ``grace_*`` modes remain available via
    ``detection_mode`` for sensitivity analysis.

    NNA definitions (CURIE-003):
    - ``naive_nna`` / ``governed_nna``: alerts / path TP stays
    - ``interruptive_nna``: interruptive alerts / interruptive TP stays
    - ``interruptive_nna_per_governed_tp``: pages / any-governed TP (legacy page burden)
    """
    sepsis = [r for r in rows if r["sepsis"]]
    non = [r for r in rows if not r["sepsis"]]
    if detection_mode is not None:
        mode: DetectionMode = detection_mode
    else:
        mode = f"window_m{window_before}_p{window_after}"

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

    # Legacy unbounded lead (first alert anywhere) — sensitivity analysis only
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

    # Primary lead: onset - first alert *inside* the detection window
    win_before, win_after = window_before, window_after
    parsed = parse_window_mode(mode)
    if parsed is not None:
        win_before, win_after = parsed

    lead_gov_window: list[float] = []
    for r in sepsis:
        onset = r.get("onset_iculos")
        hours = r.get("governed_alert_hours")
        if hours is None and r.get("first_governed_iculos") is not None:
            hours = [r["first_governed_iculos"]]
        first_in = first_alert_in_window(
            hours, onset, before=win_before, after=win_after
        )
        if first_in is not None and onset is not None:
            lead_gov_window.append(onset - first_in)

    n_sepsis = len(sepsis)
    patient_hours = sum(int(r.get("hours") or 0) for r in rows)
    patient_days = patient_hours / 24.0 if patient_hours else 0.0

    def _pct(xs: list[float | int], p: float) -> float | None:
        if not xs:
            return None
        s = sorted(float(x) for x in xs)
        return _percentile(s, p)

    timing_counts = {
        "in_window": 0,
        "too_early": 0,
        "late": 0,
        "outside_window": 0,
        "missed": 0,
    }
    for r in sepsis:
        hours = r.get("governed_alert_hours")
        if hours is None and r.get("first_governed_iculos") is not None:
            hours = [r["first_governed_iculos"]]
        cls = classify_timing(
            hours, r.get("onset_iculos"), before=win_before, after=win_after
        )
        if cls in timing_counts:
            timing_counts[cls] += 1

    # Legacy grace companion (always grace_hours) for sensitivity analysis
    legacy_mode = f"grace_{grace_hours}"
    legacy_gov_tp = sum(
        1 for r in sepsis if is_detected(r, path="governed", mode=legacy_mode)
    )
    early_gov_tp = sum(
        1 for r in sepsis if is_detected(r, path="governed", mode="early_only")
    )
    window_pm12_gov_tp = sum(
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
    interruptive_nna = ratio(
        interruptive_alerts,
        interruptive_tp,
        unit="interruptive_alerts_per_interruptive_tp_stay",
    )
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
        "timing": {
            "freeze_id": "challenge2019-label-window-m12-p6.v1",
            "label_start_note": (
                "Challenge SepsisLabel begins ~6h before clinical onset; "
                "onset_iculos is label_start."
            ),
            "window_before_hours": win_before,
            "window_after_hours": win_after,
            "primary_rule": (
                f"any alert in [label_start-{win_before}h, label_start+{win_after}h]"
            ),
            "co_primary": "challenge_utility",
            "governed_classes": timing_counts,
            "legacy_grace_hours": grace_hours,
            "legacy_grace_governed_tp": legacy_gov_tp,
            "legacy_grace_governed_sensitivity": (
                (legacy_gov_tp / n_sepsis) if n_sepsis else None
            ),
        },
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
            "window_pm12_governed_tp": window_pm12_gov_tp,
            "window_pm12_governed_sensitivity": (
                (window_pm12_gov_tp / n_sepsis) if n_sepsis else None
            ),
            "naive_fp_non_sepsis": naive_fp,
            "governed_fp_non_sepsis": gov_fp,
            "interruptive_fp_non_sepsis": interruptive_fp,
            "governed_ppv_stay": stay_ppv_governed["value"],
            "interruptive_ppv_stay": stay_ppv_interruptive["value"],
            "naive_nna": naive_nna["value"],
            "governed_nna": governed_nna["value"],
            "interruptive_nna": interruptive_nna["value"],
            "interruptive_nna_per_governed_tp": interruptive_nna_per_governed_tp[
                "value"
            ],
            # Primary lead time (bounded window)
            "mean_lead_hours_governed_in_window": _mean(lead_gov_window),
            "lead_hours_governed_in_window_p25": _pct(lead_gov_window, 0.25),
            "lead_hours_governed_in_window_p50": _pct(lead_gov_window, 0.50),
            "lead_hours_governed_in_window_p75": _pct(lead_gov_window, 0.75),
            # Legacy unbounded first-alert lead (sensitivity analysis)
            "mean_lead_hours_naive": _mean(lead_naive),
            "mean_lead_hours_governed": _mean(lead_gov),
            "mean_lead_hours_interruptive": _mean(lead_interruptive),
            "lead_hours_governed_p25": _pct(lead_gov, 0.25),
            "lead_hours_governed_p50": _pct(lead_gov, 0.50),
            "lead_hours_governed_p75": _pct(lead_gov, 0.75),
            "mean_lead_hours_governed_note": (
                "Legacy: onset − first alert anywhere (unbounded early). "
                "Primary: mean_lead_hours_governed_in_window."
            ),
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
                    "note": (
                        "Episode-level PPV uses CURIE-012 EpisodeArbiter "
                        "page emissions as the unit (see eval/episodes/)."
                    ),
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
    ("detection", "mean_lead_hours_governed_in_window"),
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
