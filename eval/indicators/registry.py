"""Indicator plugin registry — maps rule bundle score.type → scorer.

Phase 3 proof: adding AKI is a new scorer + rule bundle entry, not a platform rewrite.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

BUNDLES_DIR = (
    Path(__file__).resolve().parents[2] / "streaming" / "rule-registry" / "bundles"
)

ScorerFn = Callable[..., Any]


def load_rule_bundle(bundle_id: str, version: str | None = None) -> dict[str, Any]:
    matches = sorted(BUNDLES_DIR.glob(f"{bundle_id}.v*.json"))
    if version:
        path = BUNDLES_DIR / f"{bundle_id}.v{version}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text())
    if not matches:
        raise FileNotFoundError(f"No bundles for {bundle_id} in {BUNDLES_DIR}")
    return json.loads(matches[-1].read_text())


def list_indicators() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for path in sorted(BUNDLES_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        out.append(
            {
                "bundle_id": data["bundle_id"],
                "version": data["version"],
                "indicator": data["indicator"],
                "score_type": data.get("score", {}).get("type", ""),
                "path": str(path),
            }
        )
    return out


def governance_config_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Extract governance knobs for the shared Python governance mirror."""
    g = bundle.get("governance") or {}
    traj = g.get("trajectory") or {}
    base = g.get("baseline") or {}
    dedup = g.get("dedup") or {}
    supp = g.get("suppression") or {}
    tier = g.get("tiering") or {}
    return {
        "trajectory_persistence_minutes": traj.get("min_persistence_minutes", 30),
        "min_crossings": traj.get("min_crossings", 2),
        "baseline_enabled": base.get("enabled", True),
        "baseline_delta_threshold": base.get("delta_threshold", 2),
        "refractory_minutes": dedup.get("refractory_minutes", 120),
        "suppression_flags": set(supp.get("flags") or []),
        "interruptive_tiers": set(tier.get("interruptive_tiers") or ["urgent", "critical"]),
        "passive_tiers": set(tier.get("passive_tiers") or ["watch"]),
    }
