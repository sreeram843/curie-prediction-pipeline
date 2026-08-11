"""Python mirror of GovernancePolicy for replay harness / alert-reduction metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GovernanceConfig:
    trajectory_persistence_minutes: int = 30
    min_crossings: int = 2
    baseline_enabled: bool = True
    baseline_delta_threshold: int = 2
    refractory_minutes: int = 120
    suppression_flags: set[str] = field(
        default_factory=lambda: {"comfort_care", "already_on_sepsis_protocol"}
    )
    interruptive_tiers: set[str] = field(default_factory=lambda: {"urgent", "critical"})
    passive_tiers: set[str] = field(default_factory=lambda: {"watch"})


@dataclass
class PatientGovState:
    last_emitted_event_time: datetime | None = None
    crossings_above_threshold: int = 0
    first_crossing_event_time: datetime | None = None
    baseline_score: int | None = None
    context_flags: set[str] = field(default_factory=set)


@dataclass
class Decision:
    emit: bool
    reason: str
    routing: str
    alert: dict


def evaluate(alert: dict, state: PatientGovState, config: GovernanceConfig) -> Decision:
    score = alert.get("score")
    event_time = datetime.fromisoformat(str(alert["event_time"]).replace("Z", "+00:00"))
    out = dict(alert)
    out["governance_path"] = "governed"

    for flag in state.context_flags:
        if flag in config.suppression_flags:
            out["suppressed"] = True
            out["suppression_reason"] = f"context:{flag}"
            return Decision(False, out["suppression_reason"], "none", out)

    if state.first_crossing_event_time is None:
        state.first_crossing_event_time = event_time
        state.crossings_above_threshold = 1
    else:
        state.crossings_above_threshold += 1

    persisted_min = (event_time - state.first_crossing_event_time).total_seconds() / 60.0
    if (
        state.crossings_above_threshold < config.min_crossings
        or persisted_min < config.trajectory_persistence_minutes
    ):
        out["suppressed"] = True
        out["suppression_reason"] = "trajectory_not_met"
        return Decision(False, "trajectory_not_met", "none", out)

    if config.baseline_enabled:
        if state.baseline_score is None:
            state.baseline_score = score
            out["suppressed"] = True
            out["suppression_reason"] = "baseline_init"
            return Decision(False, "baseline_init", "none", out)
        if score is not None and (score - state.baseline_score) < config.baseline_delta_threshold:
            out["suppressed"] = True
            out["suppression_reason"] = "below_baseline_delta"
            return Decision(False, "below_baseline_delta", "none", out)

    if state.last_emitted_event_time is not None:
        refractory_min = (event_time - state.last_emitted_event_time).total_seconds() / 60.0
        if refractory_min < config.refractory_minutes:
            out["suppressed"] = True
            out["suppression_reason"] = "refractory"
            return Decision(False, "refractory", "none", out)

    tier = (alert.get("tier") or "none").lower()
    if tier in config.interruptive_tiers:
        routing = "interruptive"
    elif tier in config.passive_tiers:
        routing = "passive"
    else:
        routing = "none"

    out["suppressed"] = False
    out["suppression_reason"] = None
    state.last_emitted_event_time = event_time
    return Decision(True, "pass", routing, out)


def alert_reduction_ratio(naive_count: int, governed_count: int) -> float:
    if naive_count == 0:
        return 0.0
    return governed_count / naive_count
