"""Typed vasopressor dose conversion + weight resolution for MIMIC-IV (CURIE-051 / plan B1).

Policy (frozen in plan B1):
- ``mcg/kg/min`` -> numeric rate unchanged;
- ``mcg/min``     -> divide by valid contemporaneous weight in kg;
- ``mg/kg/min``   -> multiply by 1000;
- ``mg/min``      -> multiply by 1000, then divide by valid weight;
- ``mL/hour`` or other volume rates -> unknown unless a documented concentration exists;
- missing, non-finite, zero/negative, unsupported values, or missing/invalid/future-only
  weight -> unknown with an explicit reason.

Every conversion returns a :class:`PressorDose` carrying the dose, known flag, reason,
source unit, source rate, weight used, and evidence IDs — never a bare number.

Weight is resolved by :func:`latest_weight_before` under an availability-time rule:
the latest charted weight at or before the event time. A future-only weight is
"only_future" (never used), and there is never a silent population-default substitution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from ingestion.adapters.mimic.item_map import INPUT_VASOPRESSORS

_WEIGHT_VALID_MIN_KG = 1.0
_WEIGHT_VALID_MAX_KG = 500.0

# chartevents itemid -> kg multiplier (226531 is recorded in lbs)
WEIGHT_ITEMIDS: dict[int, float] = {
    224639: 1.0,  # Daily Weight (kg)
    226512: 1.0,  # Admission Weight (Kg)
    226531: 0.45359237,  # Admission Weight (lbs.)
}

# Order categories that are boluses, not continuous infusions. These rows keep
# the pressor "present" but never contribute a continuous dose (fail closed:
# dose unknown, never a fabricated mcg/kg/min).
_BOLUS_ORDER_CATEGORIES = frozenset({"05-Med Bolus"})

# Units that already carry a valid normalized dose on the demo-schema/harness
# path (emitted by the adapters after conversion). Any other non-empty unit
# must never be read as mcg/kg/min.
_NORMALIZED_UNITS = frozenset({"mcg/kg/min", "ug/kg/min", "μg/kg/min", ""})


@dataclass(frozen=True)
class PressorDose:
    """Explicit result of a pressor rate conversion. Never a bare number."""

    dose_ug_kg_min: float | None
    known: bool
    reason: str
    source_unit: str | None
    source_rate: float | None = None
    weight_kg: float | None = None
    weight_evidence_id: str | None = None
    evidence_id: str | None = None
    agent: str | None = None


@dataclass(frozen=True)
class WeightResolution:
    """Latest charted weight at or before ``as_of`` under the availability-time rule."""

    weight_kg: float | None
    evidence_id: str | None
    status: str  # "resolved" | "missing" | "only_future" | "invalid"


def _normalize_unit(raw: str | None) -> str:
    text = "".join((raw or "").strip().lower().split())
    if text in {"mcg/kg/min", "ug/kg/min", "μg/kg/min", "mcg/kg/minute"}:
        return "mcg/kg/min"
    if text in {"mcg/min", "ug/min", "μg/min", "mcg/minute"}:
        return "mcg/min"
    if text in {"mg/kg/min", "mg/kg/minute"}:
        return "mg/kg/min"
    if text in {"mg/min", "mg/minute"}:
        return "mg/min"
    if text in {"ml/hour", "ml/hr", "ml/h", "mls/hour"}:
        return "ml/hour"
    if text in {"", "none", "nan"}:
        return "missing"
    return f"unsupported:{text}"


def valid_weight_kg(weight: float | None) -> bool:
    if weight is None:
        return False
    if not math.isfinite(weight):
        return False
    return _WEIGHT_VALID_MIN_KG <= weight <= _WEIGHT_VALID_MAX_KG


def is_normalized_dose_unit(unit: str | None) -> bool:
    """True when a raw value may be read as mcg/kg/min on the harness path."""
    return "".join((unit or "").strip().lower().split()) in _NORMALIZED_UNITS


def pressor_agent_for_itemid(itemid: int | str) -> str | None:
    """Agent for a MIMIC-IV inputevents itemid, or None when not a mapped pressor."""
    return INPUT_VASOPRESSORS.get(int(itemid))


def convert_pressor_dose(
    *,
    rate: float | None,
    rate_uom: str | None,
    weight_kg: float | None = None,
    weight_available: bool = True,
    weight_evidence_id: str | None = None,
    evidence_id: str | None = None,
    agent: str | None = None,
) -> PressorDose:
    """Convert an inputevents rate to mcg/kg/min under the frozen B1 policy.

    ``weight_available`` is False when the caller knows the weight could not be
    resolved under the availability-time rule (e.g. only a future weight exists).
    """
    unit = _normalize_unit(rate_uom)
    source_unit = None if unit == "missing" else unit
    base = PressorDose(
        None,
        False,
        "",
        source_unit,
        source_rate=rate,
        weight_kg=weight_kg,
        weight_evidence_id=weight_evidence_id,
        evidence_id=evidence_id,
        agent=agent,
    )

    def unknown(reason: str) -> PressorDose:
        return PressorDose(
            base.dose_ug_kg_min,
            False,
            reason,
            base.source_unit,
            source_rate=base.source_rate,
            weight_kg=base.weight_kg,
            weight_evidence_id=base.weight_evidence_id,
            evidence_id=base.evidence_id,
            agent=base.agent,
        )

    def known(dose: float, reason: str) -> PressorDose:
        return PressorDose(
            dose,
            True,
            reason,
            base.source_unit,
            source_rate=base.source_rate,
            weight_kg=base.weight_kg,
            weight_evidence_id=base.weight_evidence_id,
            evidence_id=base.evidence_id,
            agent=base.agent,
        )

    if unit == "missing":
        return unknown("missing_unit")
    if unit.startswith("unsupported:"):
        return unknown(f"unsupported_unit:{unit.split(':', 1)[1]}")
    if rate is None:
        return unknown("missing_rate")
    if not math.isfinite(rate):
        return unknown("non_finite_rate")
    if rate <= 0:
        return unknown("non_positive_rate")
    if unit == "ml/hour":
        return unknown("volume_rate_without_concentration")

    if unit == "mcg/kg/min":
        return known(rate, "rate_already_weight_normalized")
    if unit == "mg/kg/min":
        return known(rate * 1000.0, "mg_to_mcg_x1000")

    needs_weight = unit in {"mcg/min", "mg/min"}
    if needs_weight:
        if not weight_available:
            return unknown("weight_unavailable_or_only_future")
        if not valid_weight_kg(weight_kg):
            return unknown("invalid_or_missing_weight")
        if unit == "mcg/min":
            return known(rate / weight_kg, "divided_by_weight_kg")
        return known((rate * 1000.0) / weight_kg, "mg_to_mcg_then_divided_by_weight_kg")

    return unknown(f"unhandled_unit:{unit}")


def latest_weight_before(
    *,
    weight_rows: list[tuple[datetime, int, float]],
    as_of: datetime,
) -> WeightResolution:
    """Resolve the latest charted weight at or before ``as_of``.

    ``weight_rows`` items are ``(charttime, itemid, valuenum_in_source_units)``;
    lbs itemids are converted to kg here. Future weights are never used.
    """
    best: tuple[datetime, float, str] | None = None
    any_future = False
    for t, itemid, value in weight_rows:
        if t > as_of:
            any_future = True
            continue
        kg = value * WEIGHT_ITEMIDS.get(itemid, 1.0)
        if best is None or t >= best[0]:
            best = (t, kg, f"MIMIC/chartevents/{itemid}/{t.strftime('%Y-%m-%d %H:%M:%S')}")
    if best is None:
        status = "only_future" if any_future else "missing"
        return WeightResolution(None, None, status)
    if not valid_weight_kg(best[1]):
        return WeightResolution(None, best[2], "invalid")
    return WeightResolution(best[1], best[2], "resolved")


def is_bolus_order_category(ordercategoryname: str | None) -> bool:
    """True for bolus/push orders that must not fabricate a continuous dose."""
    return (ordercategoryname or "").strip() in _BOLUS_ORDER_CATEGORIES
