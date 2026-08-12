"""Frozen uncertainty-band eligibility policy (CURIE-025 / LLM-WF-07)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
POLICY_PATH = FROZEN_DIR / "eligibility_policy.v1.json"

EligibilityReason = Literal[
    "near_threshold",
    "partial_completeness",
    "conflicting_components",
    "multi_signal_severity_spread",
    "watch_with_rising_score",
    "not_eligible",
]


class EligibilityPolicy(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    policy_id: str = "uncertainty-band.v1"
    mode: Literal["retrospective_passive"] = "retrospective_passive"
    # LLM / assistant must never change interruptive routing
    allow_suppress_alerts: Literal[False] = False
    allow_escalate_alerts: Literal[False] = False
    allow_change_routing: Literal[False] = False
    near_threshold_scores: list[int] = Field(default_factory=lambda: [2, 3])
    min_missing_components_for_conflict: int = 1
    min_positive_components_for_conflict: int = 1
    severity_spread_min_rank_delta: int = 2
    watch_rising_min_score: int = 2


def default_policy() -> EligibilityPolicy:
    if POLICY_PATH.is_file():
        return EligibilityPolicy.model_validate(json.loads(POLICY_PATH.read_text()))
    return EligibilityPolicy()


def write_policy(policy: EligibilityPolicy | None = None) -> Path:
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    p = policy or EligibilityPolicy()
    POLICY_PATH.write_text(json.dumps(p.model_dump(mode="json"), indent=2) + "\n")
    return POLICY_PATH


SEVERITY_RANK = {"none": 0, "watch": 1, "urgent": 2, "critical": 3}


def evaluate_eligibility(
    case: dict[str, Any],
    *,
    policy: EligibilityPolicy | None = None,
) -> dict[str, Any]:
    """Return eligibility decision for a frozen case / alert-like record."""
    pol = policy or default_policy()
    reasons: list[str] = []

    score = case.get("score")
    tier = str(case.get("tier") or case.get("dominant_severity") or "none").lower()
    completeness = str(case.get("completeness") or "partial").lower()
    missing = list(case.get("missing_components") or case.get("missing_inputs") or [])
    components = list(case.get("component_breakdown") or case.get("signals") or [])

    positive = 0
    for c in components:
        if isinstance(c, dict):
            pts = c.get("points")
            if pts is None:
                pts = c.get("score")
            missing_flag = bool(c.get("missing"))
            if not missing_flag and pts is not None and int(pts) > 0:
                positive += 1
        else:
            pts = getattr(c, "points", None) or getattr(c, "score", None)
            if pts is not None and int(pts) > 0:
                positive += 1

    if score is not None and int(score) in set(pol.near_threshold_scores):
        reasons.append("near_threshold")
    if completeness == "partial" or missing:
        reasons.append("partial_completeness")
    if (
        len(missing) >= pol.min_missing_components_for_conflict
        and positive >= pol.min_positive_components_for_conflict
    ):
        reasons.append("conflicting_components")

    # Multi-signal severity spread (episode-shaped cases)
    sevs = []
    for c in components:
        if isinstance(c, dict):
            sevs.append(str(c.get("severity") or c.get("tier") or "none").lower())
        else:
            sevs.append(str(getattr(c, "severity", "none")).lower())
    if len(sevs) >= 2:
        ranks = [SEVERITY_RANK.get(s, 0) for s in sevs]
        if max(ranks) - min(ranks) >= pol.severity_spread_min_rank_delta:
            reasons.append("multi_signal_severity_spread")

    if tier == "watch" and score is not None and int(score) >= pol.watch_rising_min_score:
        reasons.append("watch_with_rising_score")

    eligible = bool(reasons)
    return {
        "eligible": eligible,
        "reasons": reasons or ["not_eligible"],
        "policy_id": pol.policy_id,
        "mode": pol.mode,
        "allow_change_routing": pol.allow_change_routing,
        "allow_suppress_alerts": pol.allow_suppress_alerts,
        "allow_escalate_alerts": pol.allow_escalate_alerts,
    }
