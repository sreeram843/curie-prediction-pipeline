"""Pre-specified MIMIC governance ablations (CURIE-016 / protocol)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from eval.indicators.registry import load_rule_bundle
from eval.replay_harness.gov_profiles import apply_gov_knobs
from eval.replay_harness.governance import GovernanceConfig

# Full governance baseline for demo-schema study (OPS selection starts from this family).
FULL_GOVERNANCE_KNOBS: dict[str, Any] = {
    "description": "full_governance baseline for MIMIC demo-schema study",
    "trajectory_persistence_minutes": 0,
    "min_crossings": 1,
    "baseline_enabled": False,
    "baseline_delta_threshold": 2,
    "baseline_lookback_hours": 24,
    "refractory_minutes": 90,
    "min_components_required": 1,
    "naive_threshold": 2,
    "page_gate_enabled": True,
    "page_min_crossings": 2,
    "page_trajectory_persistence_minutes": 30,
    "page_min_score_delta": 1,
    "page_min_positive_components": 1,
    "use_episode_arbitration": True,
    "reject_late_out_of_order": True,
    "suppression_flags": [
        "comfort_care",
        "already_on_sepsis_protocol",
        "already_on_aki_protocol",
    ],
}

# Candidate grid for OPS-1 (development tune / calibration select). Never includes test.
SELECTION_CANDIDATES: dict[str, dict[str, Any]] = {
    "full_p90_gate": FULL_GOVERNANCE_KNOBS,
    "full_p60_gate": {
        **FULL_GOVERNANCE_KNOBS,
        "description": "shorter refractory",
        "refractory_minutes": 60,
    },
    "full_no_gate": {
        **FULL_GOVERNANCE_KNOBS,
        "description": "page gate off",
        "page_gate_enabled": False,
    },
    "strictish": {
        **FULL_GOVERNANCE_KNOBS,
        "description": "more crossings + persistence",
        "trajectory_persistence_minutes": 30,
        "min_crossings": 2,
        "baseline_enabled": True,
        "refractory_minutes": 120,
    },
}


def _ablation_knobs(name: str, patch: dict[str, Any]) -> dict[str, Any]:
    knobs = deepcopy(FULL_GOVERNANCE_KNOBS)
    knobs.update(patch)
    knobs["ablation_id"] = name
    return knobs


# Protocol pre_specified ablations (one-at-a-time from full_governance).
ABLATION_KNOBS: dict[str, dict[str, Any] | None] = {
    "threshold_only_naive": None,  # special path — no governance
    "full_governance": _ablation_knobs("full_governance", {}),
    "drop_persistence": _ablation_knobs(
        "drop_persistence", {"trajectory_persistence_minutes": 0}
    ),
    "drop_crossings": _ablation_knobs("drop_crossings", {"min_crossings": 1}),
    "drop_baseline": _ablation_knobs("drop_baseline", {"baseline_enabled": False}),
    "drop_refractory": _ablation_knobs("drop_refractory", {"refractory_minutes": 0}),
    "drop_context_suppression": _ablation_knobs(
        "drop_context_suppression", {"suppression_flags": []}
    ),
    "drop_page_gate": _ablation_knobs("drop_page_gate", {"page_gate_enabled": False}),
    "drop_episode_arbitration": _ablation_knobs(
        "drop_episode_arbitration", {"use_episode_arbitration": False}
    ),
    "drop_late_event_buffer": _ablation_knobs(
        "drop_late_event_buffer", {"reject_late_out_of_order": False}
    ),
}


def knobs_to_config(knobs: dict[str, Any]) -> tuple[dict[str, Any], GovernanceConfig]:
    bundle = load_rule_bundle("sepsis-sofa")
    bundle_out, cfg, _meta = apply_gov_knobs(bundle, knobs)
    flags = knobs.get("suppression_flags")
    if flags is not None:
        cfg.suppression_flags = set(flags)
    cfg.reject_late_out_of_order = bool(knobs.get("reject_late_out_of_order", True))
    return bundle_out, cfg


def uses_episode_arbitration(knobs: dict[str, Any] | None) -> bool:
    if knobs is None:
        return False
    return bool(knobs.get("use_episode_arbitration", True))
