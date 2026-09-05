"""Shared deterministic respiration-measurement resolution.

Room-air policy (frozen in plan B): missing oxygen documentation is never
treated as room air. Only an *explicit* room-air documentation (with its own
evidence id) may stand in for FiO2 = 0.21, and it never overrides a documented
FiO2.

SpO2/FiO2 → PaO2/FiO2 policy (frozen in plan B): the raw S/F ratio is not
compared against P/F cutoffs. For SpO2 <= 97% the Rice et al. 2007 linear
imputation (Chest 132(2):410-417) applies:

    PaO2/FiO2_est = 64 + 0.84 * (SpO2/FiO2)

For SpO2 > 97% the S/F ratio plateaus and the imputation is not reliable; the
resolver fails closed (observed-but-not-convertible) with an explicit reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

DEFAULT_RESPIRATION_LOOKBACK = timedelta(hours=24)

SFO2_IMPUTATION_CAP_PERCENT = 97.0
SFO2_IMPUTATION_INTERCEPT = 64.0
SFO2_IMPUTATION_SLOPE = 0.84
ROOM_AIR_FIO2_FRACTION = 0.21


@dataclass(frozen=True)
class RespirationResolution:
    """The scoreable PaO2/FiO2 or SpO2/FiO2 choice and its provenance.

    ``spo2_fio2`` carries the *imputed* P/F estimate when the spo2 source is
    used (or the raw SpO2/FiO2 when it can only be built from explicit room
    air). ``raw_spo2_fio2`` always holds the unadjusted SpO2/FiO2 for
    provenance, and ``spo2_imputation`` records the conversion method or the
    fail-closed reason.
    """

    source: Literal["pao2", "spo2"] | None
    pao2_fio2: float | None
    spo2_fio2: float | None
    evidence_ids: tuple[str, ...]
    raw_spo2_fio2: float | None = None
    spo2_imputation: str | None = None


def impute_pf_from_spo2(
    *,
    spo2_percent: float | None,
    fio2_fraction: float | None,
) -> tuple[float | None, str | None]:
    """Rice 2007 linear S/F → P/F imputation; fails closed outside its validity.

    Returns ``(imputed_pf, method)`` where method is ``"rice2007_linear"``,
    ``"spo2_gt_97_no_imputation"``, or ``None`` when inputs are invalid.
    """
    if spo2_percent is None or fio2_fraction is None:
        return None, None
    if spo2_percent <= 0 or spo2_percent > 100:
        return None, None
    if fio2_fraction <= 0:
        return None, None
    if spo2_percent > SFO2_IMPUTATION_CAP_PERCENT:
        return None, "spo2_gt_97_no_imputation"
    sf = spo2_percent / fio2_fraction
    return SFO2_IMPUTATION_INTERCEPT + SFO2_IMPUTATION_SLOPE * sf, "rice2007_linear"


def _within_window(
    *,
    observed_at: datetime | None,
    fio2_observed_at: datetime | None,
    as_of: datetime | None,
    lookback: timedelta,
) -> bool:
    if observed_at is None or fio2_observed_at is None:
        return False
    if as_of is not None and (observed_at > as_of or fio2_observed_at > as_of):
        return False
    return abs(observed_at - fio2_observed_at) <= lookback


def resolve_spo2_fio2_pao2(
    *,
    pao2_mmhg: float | None,
    pao2_observed_at: datetime | None,
    pao2_evidence_id: str | None,
    spo2_percent: float | None,
    spo2_observed_at: datetime | None,
    spo2_evidence_id: str | None,
    fio2_fraction: float | None,
    fio2_observed_at: datetime | None,
    fio2_evidence_id: str | None,
    as_of: datetime | None = None,
    lookback: timedelta = DEFAULT_RESPIRATION_LOOKBACK,
    explicit_room_air: bool = False,
    room_air_evidence_id: str | None = None,
    room_air_observed_at: datetime | None = None,
) -> RespirationResolution:
    """Resolve one respiration ratio with a shared preference and time policy.

    PaO2 is preferred when it can be paired with FiO2. SpO2 is the fallback.
    Missing oxygen documentation is never treated as room air; an explicit
    room-air observation (with evidence and time) may stand in for FiO2 = 0.21.
    No other ambient-air FiO2 is inferred, and observations outside the
    lookback or unavailable at ``as_of`` are not paired.
    """
    documented_fio2 = fio2_fraction is not None and fio2_fraction > 0

    if documented_fio2:
        fio2_frac = fio2_fraction
        fio2_eid = fio2_evidence_id
        pairing_time = fio2_observed_at
    elif explicit_room_air and room_air_evidence_id and room_air_observed_at is not None:
        fio2_frac = ROOM_AIR_FIO2_FRACTION
        fio2_eid = room_air_evidence_id
        pairing_time = room_air_observed_at
    else:
        return RespirationResolution(None, None, None, ())

    if pao2_mmhg is not None and pao2_mmhg > 0 and _within_window(
        observed_at=pao2_observed_at,
        fio2_observed_at=pairing_time,
        as_of=as_of,
        lookback=lookback,
    ):
        eids = tuple(e for e in (pao2_evidence_id, fio2_eid) if e)
        return RespirationResolution("pao2", pao2_mmhg / fio2_frac, None, eids)

    if spo2_percent is not None and _within_window(
        observed_at=spo2_observed_at,
        fio2_observed_at=pairing_time,
        as_of=as_of,
        lookback=lookback,
    ):
        raw_sf = spo2_percent / fio2_frac
        imputed, method = impute_pf_from_spo2(
            spo2_percent=spo2_percent, fio2_fraction=fio2_frac
        )
        eids = tuple(e for e in (spo2_evidence_id, fio2_eid) if e)
        return RespirationResolution(
            "spo2",
            None,
            imputed,
            eids,
            raw_spo2_fio2=raw_sf,
            spo2_imputation=method,
        )

    return RespirationResolution(None, None, None, ())
