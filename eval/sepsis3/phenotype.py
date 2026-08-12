"""Sepsis-3 phenotype (prototype) — infection suspicion + acute SOFA rise.

This is **not** a bedside diagnosis and is **not** clinically validated.

Sepsis-3 (Singer et al., JAMA 2016) requires suspected infection **and** an acute
increase in SOFA of ≥2. Absolute SOFA score alone is organ dysfunction
(``sofa-deterioration``), not sepsis.

Infection-suspicion timing (v1.0.0)
-----------------------------------
- ``culture``: specimen collection / order time for a microbiologic culture.
- ``antimicrobial``: first administration (or order) of a systemic antimicrobial
  used for suspected infection.
- Either event establishes suspicion time ``t_inf``.
- Acute SOFA change is evaluated using baseline vs current SOFA within
  ``[t_inf - window_before_hours, t_inf + window_after_hours]`` (default ±24h).

Pre-existing organ dysfunction without an acute Δ≥2 does **not** meet the phenotype.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

PHENOTYPE_ID = "sepsis-3"
PHENOTYPE_VERSION = "1.0.0"
MIN_SOFA_DELTA = 2
DEFAULT_WINDOW_BEFORE_HOURS = 24
DEFAULT_WINDOW_AFTER_HOURS = 24


@dataclass(frozen=True)
class InfectionEvent:
    """One culture or antimicrobial event that can establish infection suspicion."""

    event_time: datetime
    kind: Literal["culture", "antimicrobial"]
    evidence_id: str


@dataclass
class Sepsis3Input:
    """Inputs for a single phenotype evaluation at ``as_of``."""

    as_of: datetime
    current_sofa: int | None
    baseline_sofa: int | None
    infection_events: list[InfectionEvent] = field(default_factory=list)
    exclusion_flags: set[str] = field(default_factory=set)
    window_before_hours: int = DEFAULT_WINDOW_BEFORE_HOURS
    window_after_hours: int = DEFAULT_WINDOW_AFTER_HOURS


@dataclass
class Sepsis3Result:
    phenotype_id: str = PHENOTYPE_ID
    phenotype_version: str = PHENOTYPE_VERSION
    met: bool = False
    status: Literal["met", "not_met", "insufficient_data", "excluded"] = "not_met"
    criteria_met: list[str] = field(default_factory=list)
    criteria_failed: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    exclusions_applied: list[str] = field(default_factory=list)
    sofa_delta: int | None = None
    infection_time: datetime | None = None
    infection_kind: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    note: str = (
        "Prototype Sepsis-3 phenotype — not a diagnosis; SOFA alone is sofa-deterioration."
    )


_EXCLUSION_FLAGS = frozenset({"comfort_care", "already_on_sepsis_protocol"})


def _pick_infection(
    events: list[InfectionEvent],
    *,
    as_of: datetime,
    window_before: timedelta,
    window_after: timedelta,
) -> InfectionEvent | None:
    """Earliest infection event whose suspicion window covers ``as_of``."""
    eligible = [
        e
        for e in events
        if (e.event_time - window_before) <= as_of <= (e.event_time + window_after)
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda e: (e.event_time, e.evidence_id))


def evaluate_sepsis3(inp: Sepsis3Input) -> Sepsis3Result:
    """Evaluate Sepsis-3 phenotype; never returns met when inputs are incomplete."""
    out = Sepsis3Result()
    evidence: list[str] = []

    exclusions = sorted(f for f in inp.exclusion_flags if f in _EXCLUSION_FLAGS)
    if exclusions:
        out.status = "excluded"
        out.exclusions_applied = exclusions
        out.criteria_failed.append("exclusion_flag")
        return out

    if inp.current_sofa is None:
        out.status = "insufficient_data"
        out.missing_inputs.append("current_sofa")
    if inp.baseline_sofa is None:
        out.status = "insufficient_data"
        out.missing_inputs.append("baseline_sofa")

    window_before = timedelta(hours=max(0, inp.window_before_hours))
    window_after = timedelta(hours=max(0, inp.window_after_hours))
    infection = _pick_infection(
        inp.infection_events,
        as_of=inp.as_of,
        window_before=window_before,
        window_after=window_after,
    )
    if infection is None:
        if not inp.infection_events:
            out.missing_inputs.append("infection_suspicion")
            out.status = "insufficient_data"
        else:
            out.criteria_failed.append("infection_outside_window")
            if out.status != "insufficient_data":
                out.status = "not_met"
    else:
        out.criteria_met.append(f"infection_{infection.kind}")
        out.infection_time = infection.event_time
        out.infection_kind = infection.kind
        evidence.append(infection.evidence_id)

    if inp.current_sofa is not None and inp.baseline_sofa is not None:
        delta = int(inp.current_sofa) - int(inp.baseline_sofa)
        out.sofa_delta = delta
        if delta >= MIN_SOFA_DELTA:
            out.criteria_met.append("acute_sofa_rise_ge_2")
        else:
            out.criteria_failed.append("acute_sofa_rise_ge_2")
            # Explicit: chronic/high baseline without acute rise is not sepsis-3
            if inp.baseline_sofa >= 2 and delta < MIN_SOFA_DELTA:
                out.criteria_failed.append("pre_existing_dysfunction_without_acute_rise")

    out.evidence_ids = evidence

    if out.status == "insufficient_data":
        out.met = False
        return out

    if out.status == "excluded":
        out.met = False
        return out

    infection_ok = any(c.startswith("infection_") for c in out.criteria_met)
    sofa_ok = "acute_sofa_rise_ge_2" in out.criteria_met
    if infection_ok and sofa_ok:
        out.met = True
        out.status = "met"
    else:
        out.met = False
        out.status = "not_met"
        if not infection_ok and "infection_outside_window" not in out.criteria_failed:
            if "infection_suspicion" not in out.missing_inputs:
                out.criteria_failed.append("infection_suspicion")
    return out
