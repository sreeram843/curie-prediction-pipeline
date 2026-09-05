"""Shared deterministic respiration-measurement resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

DEFAULT_RESPIRATION_LOOKBACK = timedelta(hours=24)


@dataclass(frozen=True)
class RespirationResolution:
    """The scoreable PaO2/FiO2 or SpO2/FiO2 choice and its provenance."""

    source: Literal["pao2", "spo2"] | None
    pao2_fio2: float | None
    spo2_fio2: float | None
    evidence_ids: tuple[str, ...]


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
) -> RespirationResolution:
    """Resolve one respiration ratio with a shared preference and time policy.

    PaO2 is preferred when it can be paired with FiO2.  SpO2 is the fallback.
    No ambient-air FiO2 is inferred, and observations outside the lookback or
    unavailable at ``as_of`` are not paired.
    """
    if fio2_fraction is None or fio2_fraction <= 0:
        return RespirationResolution(None, None, None, ())

    if pao2_mmhg is not None and pao2_mmhg > 0 and _within_window(
        observed_at=pao2_observed_at,
        fio2_observed_at=fio2_observed_at,
        as_of=as_of,
        lookback=lookback,
    ):
        eids = tuple(e for e in (pao2_evidence_id, fio2_evidence_id) if e)
        return RespirationResolution("pao2", pao2_mmhg / fio2_fraction, None, eids)

    if spo2_percent is not None and _within_window(
        observed_at=spo2_observed_at,
        fio2_observed_at=fio2_observed_at,
        as_of=as_of,
        lookback=lookback,
    ):
        eids = tuple(e for e in (spo2_evidence_id, fio2_evidence_id) if e)
        return RespirationResolution("spo2", None, spo2_percent / fio2_fraction, eids)

    return RespirationResolution(None, None, None, ())
