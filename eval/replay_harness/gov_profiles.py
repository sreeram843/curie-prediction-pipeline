"""Named governance profiles for eval / Challenge 2019.

``accuracy`` prioritizes detection (sensitivity) over minimal alert volume.
``strict`` matches sepsis-sofa v0.2 bundle defaults (interrupt hygiene).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from eval.replay_harness.governance import GovernanceConfig

GovProfileName = Literal["strict", "balanced", "sensitive", "accuracy", "dual"]

# accuracy ≈ sensitive with short refractory; best catch rate we expose as a named preset.
PROFILES: dict[str, dict[str, Any]] = {
    "strict": {
        "description": "Bundle defaults — minimize interrupts",
        "trajectory_persistence_minutes": 30,
        "min_crossings": 2,
        "baseline_enabled": True,
        "baseline_delta_threshold": 2,
        "baseline_lookback_hours": 24,
        "refractory_minutes": 120,
        "min_components_required": 3,
        "naive_threshold": None,  # use bundle
        "page_gate_enabled": False,
    },
    "balanced": {
        "description": "Moderate recall / burden tradeoff",
        "trajectory_persistence_minutes": 15,
        "min_crossings": 1,
        "baseline_enabled": True,
        "baseline_delta_threshold": 2,
        "baseline_lookback_hours": 24,
        "refractory_minutes": 60,
        "min_components_required": 2,
        "naive_threshold": None,
        "page_gate_enabled": True,
        "page_min_crossings": 2,
        "page_trajectory_persistence_minutes": 30,
        "page_min_score_delta": 1,
        "page_min_positive_components": 2,
    },
    "sensitive": {
        "description": "High recall; light dedup (hourly-friendly refractory)",
        "trajectory_persistence_minutes": 0,
        "min_crossings": 1,
        "baseline_enabled": False,
        "baseline_delta_threshold": 2,
        "baseline_lookback_hours": 24,
        # Challenge rows are hourly — refractory must be >= 60m to suppress consecutive hours.
        "refractory_minutes": 120,
        "min_components_required": 2,
        "naive_threshold": None,
        "page_gate_enabled": False,
    },
    "accuracy": {
        "description": "Best detection with light hourly dedup (prefer recall over silence)",
        "trajectory_persistence_minutes": 0,
        "min_crossings": 1,
        "baseline_enabled": False,
        "baseline_delta_threshold": 1,
        "baseline_lookback_hours": 24,
        # Emit on first qualifying hour; then ~1 alert / hour with 61+ refractory.
        # 60m does not block exact 1h spacing (< check); use 90m ≈ every other hour.
        "refractory_minutes": 90,
        "min_components_required": 2,
        "naive_threshold": 2,
        "page_gate_enabled": False,
    },
    "dual": {
        "description": (
            "Detection-first watch lane + harder page gate "
            "(rising score, ≥2 crossings, ≥2 positive components)"
        ),
        "trajectory_persistence_minutes": 0,
        "min_crossings": 1,
        "baseline_enabled": False,
        "baseline_delta_threshold": 1,
        "baseline_lookback_hours": 24,
        "refractory_minutes": 90,
        "min_components_required": 2,
        "naive_threshold": 2,
        "page_gate_enabled": True,
        "page_min_crossings": 2,
        "page_trajectory_persistence_minutes": 60,
        "page_min_score_delta": 1,
        "page_min_positive_components": 2,
    },
}


def apply_gov_knobs(
    bundle: dict[str, Any],
    knobs: dict[str, Any],
    *,
    base_config: GovernanceConfig | None = None,
) -> tuple[dict[str, Any], GovernanceConfig, dict[str, Any]]:
    """Apply a knob dict (profile meta or frozen sidecar) to bundle + GovernanceConfig."""
    meta = dict(knobs)
    b = deepcopy(bundle)
    if meta.get("min_components_required") is not None:
        b.setdefault("score", {})["min_components_required"] = meta["min_components_required"]
    if meta.get("naive_threshold") is not None:
        b.setdefault("alert", {})["naive_threshold"] = meta["naive_threshold"]

    cfg = base_config or GovernanceConfig()
    cfg.trajectory_persistence_minutes = int(meta["trajectory_persistence_minutes"])
    cfg.min_crossings = int(meta["min_crossings"])
    cfg.baseline_enabled = bool(meta["baseline_enabled"])
    cfg.baseline_delta_threshold = int(meta.get("baseline_delta_threshold", 2))
    cfg.baseline_lookback_hours = int(meta.get("baseline_lookback_hours", 24))
    cfg.refractory_minutes = int(meta["refractory_minutes"])
    cfg.page_gate_enabled = bool(meta.get("page_gate_enabled", False))
    cfg.page_min_crossings = int(meta.get("page_min_crossings", 2))
    cfg.page_trajectory_persistence_minutes = int(
        meta.get("page_trajectory_persistence_minutes", 30)
    )
    cfg.page_min_score_delta = int(meta.get("page_min_score_delta", 1))
    cfg.page_min_positive_components = int(meta.get("page_min_positive_components", 0))
    g = bundle.get("governance") or {}
    supp = g.get("suppression") or {}
    if supp.get("flags"):
        cfg.suppression_flags = set(supp["flags"])
    return b, cfg, meta


def apply_gov_profile(
    bundle: dict[str, Any],
    profile: str,
    *,
    base_config: GovernanceConfig | None = None,
) -> tuple[dict[str, Any], GovernanceConfig, dict[str, Any]]:
    """Return (bundle_copy, gov_config, profile_meta)."""
    if profile not in PROFILES:
        raise ValueError(f"Unknown gov profile {profile!r}; choose from {sorted(PROFILES)}")
    return apply_gov_knobs(bundle, PROFILES[profile], base_config=base_config)
