"""Python mirror of GovernancePolicy for replay harness / alert-reduction metrics.

Context suppression flags (e.g. ``comfort_care``) are **encounter-scoped**: they accumulate
within an encounter and clear when ``encounter_id`` changes.

Dual-lane (optional ``page_gate_enabled``): watch/passive can fire once shared trajectory /
baseline / refractory gates pass; interruptive (page) requires extra page gates. If the score
tier is interruptive but page gates fail, the alert is still emitted as **passive** (watch)
so detection recall is preserved while pages stay quieter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GovernanceConfig:
    trajectory_persistence_minutes: int = 30
    min_crossings: int = 2
    baseline_enabled: bool = True
    baseline_delta_threshold: int = 2
    baseline_lookback_hours: int = 24
    refractory_minutes: int = 120
    resolution_gap_minutes: int = 60
    suppression_flags: set[str] = field(
        default_factory=lambda: {"comfort_care", "already_on_sepsis_protocol"}
    )
    interruptive_tiers: set[str] = field(default_factory=lambda: {"urgent", "critical"})
    passive_tiers: set[str] = field(default_factory=lambda: {"watch"})
    # Dual-lane page gate (off = legacy: tier maps directly to routing)
    page_gate_enabled: bool = False
    page_min_crossings: int = 2
    page_trajectory_persistence_minutes: int = 30
    page_min_score_delta: int = 1  # vs first crossing score in streak; 0 disables
    page_min_positive_components: int = 0  # 0 disables; uses alert["positive_components"]


@dataclass
class PatientGovState:
    last_emitted_event_time: datetime | None = None
    crossings_above_threshold: int = 0
    first_crossing_event_time: datetime | None = None
    last_crossing_event_time: datetime | None = None
    first_crossing_score: int | None = None
    baseline_score: int | None = None
    baseline_set_at: datetime | None = None
    encounter_id: str | None = None
    last_processed_event_time: datetime | None = None
    context_flags: set[str] = field(default_factory=set)

    def reset_trajectory(self) -> None:
        self.crossings_above_threshold = 0
        self.first_crossing_event_time = None
        self.last_crossing_event_time = None
        self.first_crossing_score = None


@dataclass
class Decision:
    emit: bool
    reason: str
    routing: str
    alert: dict


def note_below_threshold(state: PatientGovState) -> None:
    """Call when score drops below naive threshold (recovery)."""
    state.reset_trajectory()


def _normalize_encounter_id(encounter_id: object | None) -> str | None:
    if encounter_id is None:
        return None
    text = str(encounter_id).strip()
    return text or None


def _apply_encounter_scope(state: PatientGovState, encounter_id: object | None) -> None:
    """Bind state to an encounter; clear encounter-scoped fields on identity change.

    Missing/blank ``encounter_id`` keeps the current scope (sticky within a stream).
    Transition ``None → Encounter/X`` counts as a change so flags set before any
    encounter id cannot leak into the first named encounter.
    """
    new_id = _normalize_encounter_id(encounter_id)
    if new_id is None:
        return
    if state.encounter_id == new_id:
        return
    state.reset_trajectory()
    state.baseline_score = None
    state.baseline_set_at = None
    state.last_emitted_event_time = None
    # Context flags are encounter-scoped (e.g. comfort_care must not leak).
    state.context_flags.clear()
    state.encounter_id = new_id


def _page_gates_met(
    *,
    state: PatientGovState,
    config: GovernanceConfig,
    score: int,
    alert: dict,
    persisted_min: float,
) -> tuple[bool, str | None]:
    """Return (ok, defer_reason)."""
    if not config.page_gate_enabled:
        return True, None
    if state.crossings_above_threshold < config.page_min_crossings:
        return False, "page_crossings"
    if persisted_min < config.page_trajectory_persistence_minutes:
        return False, "page_persistence"
    if config.page_min_score_delta > 0 and state.first_crossing_score is not None:
        if int(score) - int(state.first_crossing_score) < config.page_min_score_delta:
            return False, "page_not_rising"
    if config.page_min_positive_components > 0:
        pos = alert.get("positive_components")
        if pos is None or int(pos) < config.page_min_positive_components:
            return False, "page_components"
    return True, None


def evaluate(alert: dict, state: PatientGovState, config: GovernanceConfig) -> Decision:
    score = alert.get("score")
    event_time = datetime.fromisoformat(str(alert["event_time"]).replace("Z", "+00:00"))
    out = dict(alert)
    out["governance_path"] = "governed"

    # Explicit late-data policy: ignore out-of-order arrivals without mutating state.
    if state.last_processed_event_time is not None and event_time < state.last_processed_event_time:
        out["suppressed"] = True
        out["suppression_reason"] = "late_out_of_order"
        return Decision(False, "late_out_of_order", "none", out)
    state.last_processed_event_time = event_time

    _apply_encounter_scope(state, alert.get("encounter_id"))

    incoming_flags = {str(f) for f in (alert.get("context_flags") or [])}
    state.context_flags |= incoming_flags

    tier = (alert.get("tier") or "none").lower()
    if tier == "none" or score is None:
        note_below_threshold(state)
        out["suppressed"] = True
        out["suppression_reason"] = "below_threshold"
        return Decision(False, "below_threshold", "none", out)

    flags = set(state.context_flags) | incoming_flags
    for flag in flags:
        if flag in config.suppression_flags:
            out["suppressed"] = True
            out["suppression_reason"] = f"context:{flag}"
            return Decision(False, out["suppression_reason"], "none", out)

    if (
        config.baseline_enabled
        and state.baseline_score is not None
        and state.baseline_set_at is not None
    ):
        age_h = (event_time - state.baseline_set_at).total_seconds() / 3600.0
        if age_h > config.baseline_lookback_hours:
            state.baseline_score = None
            state.baseline_set_at = None

    if state.last_crossing_event_time is not None:
        gap_min = (event_time - state.last_crossing_event_time).total_seconds() / 60.0
        if gap_min > config.resolution_gap_minutes:
            state.reset_trajectory()

    # Unique event-time crossings only
    if state.last_crossing_event_time != event_time:
        if state.first_crossing_event_time is None:
            state.first_crossing_event_time = event_time
            state.first_crossing_score = int(score)
            state.crossings_above_threshold = 1
        else:
            state.crossings_above_threshold += 1
        state.last_crossing_event_time = event_time

    persisted_min = (
        (event_time - state.first_crossing_event_time).total_seconds() / 60.0
        if state.first_crossing_event_time
        else 0.0
    )
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
            state.baseline_set_at = event_time
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

    page_ok, page_defer = _page_gates_met(
        state=state,
        config=config,
        score=int(score),
        alert=alert,
        persisted_min=persisted_min,
    )

    if tier in config.interruptive_tiers:
        if page_ok:
            routing = "interruptive"
            reason = "pass"
        else:
            # Dual-lane: still notify via watch; defer the page.
            routing = "passive"
            reason = f"pass_watch:{page_defer}"
            out["page_deferred_reason"] = page_defer
    elif tier in config.passive_tiers:
        routing = "passive"
        reason = "pass"
    else:
        routing = "none"
        reason = "pass"

    out["suppressed"] = False
    out["suppression_reason"] = None
    state.last_emitted_event_time = event_time
    return Decision(True, reason, routing, out)


def alert_reduction_ratio(naive_count: int, governed_count: int) -> float:
    if naive_count == 0:
        return 0.0
    return governed_count / naive_count
