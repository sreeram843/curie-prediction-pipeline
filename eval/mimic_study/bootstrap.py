"""Bootstrap confidence intervals (protocol v1: 1000 stay-level replicates, seed 42)."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

BOOTSTRAP_N_REPLICATES = 1000
BOOTSTRAP_SEED = 42


def bootstrap_percentile_ci(
    stat_fn: Callable[[list[Any]], float],
    units: list[Any],
    *,
    n_replicates: int = BOOTSTRAP_N_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float]:
    """Percentile 95% CI for a stay-level statistic via seeded bootstrap."""
    rng = random.Random(seed)
    n = len(units)
    if n == 0:
        return {"point": float("nan"), "lo_2p5": float("nan"), "hi_97p5": float("nan"),
                "n_units": 0}
    point = stat_fn(units)
    replicates: list[float] = []
    for _ in range(n_replicates):
        idx = [rng.randrange(n) for _ in range(n)]
        sample = [units[i] for i in idx]
        try:
            replicates.append(stat_fn(sample))
        except ZeroDivisionError:
            replicates.append(float("nan"))
    finite = [r for r in replicates if r == r]
    if not finite:
        return {"point": point, "lo_2p5": float("nan"), "hi_97p5": float("nan"),
                "n_units": n, "finite_replicates": 0}
    finite.sort()
    lo = finite[int(0.025 * (len(finite) - 1))]
    hi = finite[int(0.975 * (len(finite) - 1))]
    return {
        "point": point,
        "lo_2p5": lo,
        "hi_97p5": hi,
        "n_units": n,
        "finite_replicates": len(finite),
        "n_replicates": n_replicates,
        "seed": seed,
    }


def sensitivity_in_window(
    labeled_positive_stays: list[dict[str, Any]],
    *,
    alert_times_key: str = "alert_times",
    onset_key: str = "onset",
    window_before_hours: float = 12.0,
    window_after_hours: float = 6.0,
) -> float:
    """Fraction of labeled-positive stays with >=1 alert in [onset - before, onset + after].

    Pure audit scaffolding; alert/onset values must come from a frozen label run.
    """
    if not labeled_positive_stays:
        raise ZeroDivisionError("no labeled-positive stays")
    hits = 0
    for stay in labeled_positive_stays:
        onset = float(stay[onset_key])
        lo = onset - window_before_hours * 3600
        hi = onset + window_after_hours * 3600
        if any(lo <= float(t) <= hi for t in stay.get(alert_times_key) or []):
            hits += 1
    return hits / len(labeled_positive_stays)
