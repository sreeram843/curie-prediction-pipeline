"""Resolved Challenge 2019 study bundles (immutable eval artifacts).

Product rule bundles live under ``streaming/rule-registry/bundles/``.
Study artifacts live under ``eval/challenge2019/frozen/`` and must not be
confused with product ``sepsis-sofa`` versions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.indicators.registry import content_hash
from eval.replay_harness.gov_profiles import apply_gov_knobs
from eval.replay_harness.governance import GovernanceConfig

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
STUDY_BUNDLE_V1 = FROZEN_DIR / "sepsis-sofa.challenge2019-p1.v1.json"
STUDY_BUNDLE_V1_SHA = FROZEN_DIR / "sepsis-sofa.challenge2019-p1.v1.sha256"
WINNER_SIDECAR = FROZEN_DIR / "p1_setA_winner.json"


class StudyBundleError(ValueError):
    """Study artifact missing, invalid, or hash-drifted."""


def expected_content_hash(path: Path | None = None) -> str:
    sha_path = path or STUDY_BUNDLE_V1_SHA
    return sha_path.read_text().strip().split()[0]


def load_resolved_study_bundle(
    path: Path | None = None,
    *,
    verify_hash: bool = True,
) -> dict[str, Any]:
    """Load the immutable Challenge study bundle (no profile overlay)."""
    bundle_path = path or STUDY_BUNDLE_V1
    data = json.loads(bundle_path.read_text())
    if not data.get("study_artifact"):
        raise StudyBundleError(f"{bundle_path} is not marked study_artifact=true")
    if int((data.get("score") or {}).get("min_components_required") or 0) != 2:
        raise StudyBundleError(
            f"{bundle_path} must use min_components_required=2 (Challenge freeze)"
        )
    digest = content_hash({k: v for k, v in data.items() if k != "content_hash"})
    if verify_hash:
        expected = expected_content_hash()
        if digest != expected:
            raise StudyBundleError(
                f"Study bundle hash drift for {bundle_path.name}: "
                f"got {digest}, expected {expected}"
            )
    data = dict(data)
    data["content_hash"] = digest
    return data


def governance_from_study_bundle(bundle: dict[str, Any]) -> GovernanceConfig:
    """Build GovernanceConfig from a fully resolved study bundle (no knobs file)."""
    # Reuse apply_gov_knobs by projecting bundle governance → knob dict
    g = bundle.get("governance") or {}
    traj = g.get("trajectory") or {}
    base = g.get("baseline") or {}
    dedup = g.get("dedup") or {}
    page = g.get("page_gate") or {}
    knobs = {
        "trajectory_persistence_minutes": traj.get("min_persistence_minutes", 0),
        "min_crossings": traj.get("min_crossings", 1),
        "baseline_enabled": base.get("enabled", False),
        "baseline_delta_threshold": base.get("delta_threshold", 2),
        "baseline_lookback_hours": base.get("lookback_hours", 24),
        "refractory_minutes": dedup.get("refractory_minutes", 90),
        "min_components_required": (bundle.get("score") or {}).get(
            "min_components_required", 2
        ),
        "page_gate_enabled": page.get("enabled", False),
        "page_min_crossings": page.get("min_crossings", 2),
        "page_trajectory_persistence_minutes": page.get(
            "trajectory_persistence_minutes", 30
        ),
        "page_min_score_delta": page.get("min_score_delta", 1),
        "page_min_positive_components": page.get("min_positive_components", 0),
    }
    _, cfg, _ = apply_gov_knobs(bundle, knobs)
    return cfg
