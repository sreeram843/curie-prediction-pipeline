"""Tests for SpO2/FiO2 → PaO2/FiO2 imputation and room-air handling (plan B).

The cited method is the Rice et al. 2007 linear imputation
(Chest 132(2):410-417; also Pandharipande 2009, Crit Care Med 37(4):1317-21):

    PaO2/FiO2_est = 64 + 0.84 * (SpO2/FiO2),  valid for SpO2 <= 97%.

Above 97% the SpO2/FiO2 ratio plateaus and the imputation is not reliable; the
resolver fails closed (ratio None with an explicit reason) instead of guessing.

The direction is tested empirically below: for SpO2 <= 97, the raw S/F ratio is
lower than the imputed P/F wherever S/F < 400, so comparing raw S/F against the
SOFA P/F cutoffs (400/300/200/100) over-scores the severe bands.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ingestion.adapters.respiration import (
    SFO2_IMPUTATION_CAP_PERCENT,
    impute_pf_from_spo2,
    resolve_spo2_fio2_pao2,
)

# --- empirical direction of the raw-S/F vs P/F-cutoff relationship -------------


def test_raw_sf_over_scores_severe_bands_empirically() -> None:
    """Prove the direction: raw S/F < imputed P/F for S/F < 400 (over-scores)."""
    samples = [
        (88, 0.5),  # S/F 176  → imputed 211.8
        (80, 0.4),  # S/F 200  → imputed 232.0
        (92, 0.6),  # S/F 153.3 → imputed 192.8
        (95, 0.3),  # S/F 316.7 → imputed 330.0
    ]
    for spo2, fio2 in samples:
        raw = spo2 / fio2
        imputed, method = impute_pf_from_spo2(
            spo2_percent=spo2, fio2_fraction=fio2
        )
        assert method == "rice2007_linear"
        if raw < 400:
            assert imputed > raw  # raw over-scores vs P/F cutoffs
        else:
            assert imputed < raw  # raw under-scores at the top


def test_raw_sf_band_shift_against_pf_cutoffs() -> None:
    """A concrete SOFA band example: raw S/F 176 → 3 pts; imputed 211.8 → 2 pts."""
    raw = 88 / 0.5  # 176 → raw comparison puts it < 200 → 3 points
    imputed, _ = impute_pf_from_spo2(spo2_percent=88, fio2_fraction=0.5)
    bands = ((4, 100), (3, 200), (2, 300), (1, 400))  # points, upper bound (P/F)
    raw_points = next(p for p, c in bands if raw < c)
    imputed_points = next(p for p, c in bands if imputed < c)
    assert raw_points == 3
    assert imputed_points == 2
    assert raw_points > imputed_points  # over-scores by one band


def test_imputation_formula_known_values() -> None:
    # SpO2 95, FiO2 0.4 → S/F 237.5 → 64 + 0.84*237.5 = 263.5
    value, method = impute_pf_from_spo2(spo2_percent=95, fio2_fraction=0.4)
    assert method == "rice2007_linear"
    assert value == pytest.approx(263.5, abs=0.01)
    # SpO2 92, FiO2 0.28 → S/F 328.57 → 64 + 0.84*328.57 = 340.0
    value, _ = impute_pf_from_spo2(spo2_percent=92, fio2_fraction=0.28)
    assert value == pytest.approx(340.0, abs=0.1)


def test_imputation_cap_boundary_97() -> None:
    value, method = impute_pf_from_spo2(spo2_percent=97, fio2_fraction=0.3)
    assert method == "rice2007_linear"
    assert value is not None


def test_imputation_fails_closed_above_cap() -> None:
    for spo2 in (98, 99, 100):
        value, method = impute_pf_from_spo2(spo2_percent=spo2, fio2_fraction=0.4)
        assert value is None
        assert method == "spo2_gt_97_no_imputation"


def test_imputation_rejects_invalid_inputs() -> None:
    assert impute_pf_from_spo2(spo2_percent=None, fio2_fraction=0.4) == (None, None)
    assert impute_pf_from_spo2(spo2_percent=90, fio2_fraction=None) == (None, None)
    assert impute_pf_from_spo2(spo2_percent=90, fio2_fraction=0.0) == (None, None)
    assert impute_pf_from_spo2(spo2_percent=90, fio2_fraction=-0.2) == (None, None)
    assert impute_pf_from_spo2(spo2_percent=0, fio2_fraction=0.4) == (None, None)
    assert impute_pf_from_spo2(spo2_percent=101, fio2_fraction=0.4) == (None, None)


def test_cap_constant_documented_value() -> None:
    assert SFO2_IMPUTATION_CAP_PERCENT == 97.0


# --- resolver behavior ----------------------------------------------------------


def _args(**overrides):
    values = {
        "pao2_mmhg": None,
        "pao2_observed_at": None,
        "pao2_evidence_id": None,
        "spo2_percent": 88.0,
        "spo2_observed_at": datetime(2020, 1, 1, 1),
        "spo2_evidence_id": "spo2/1",
        "fio2_fraction": 0.5,
        "fio2_observed_at": datetime(2020, 1, 1, 1),
        "fio2_evidence_id": "fio2/1",
        "as_of": datetime(2020, 1, 1, 2),
    }
    values.update(overrides)
    return values


def test_resolver_emits_imputed_ratio_for_spo2_source() -> None:
    out = resolve_spo2_fio2_pao2(**_args())
    assert out.source == "spo2"
    assert out.raw_spo2_fio2 == pytest.approx(176.0)
    assert out.spo2_fio2 == pytest.approx(64 + 0.84 * 176.0)
    assert out.spo2_imputation == "rice2007_linear"
    assert out.evidence_ids == ("spo2/1", "fio2/1")


def test_resolver_fails_closed_when_spo2_above_cap() -> None:
    out = resolve_spo2_fio2_pao2(**_args(spo2_percent=99))
    assert out.source == "spo2"  # observed but not convertible
    assert out.spo2_fio2 is None
    assert out.raw_spo2_fio2 == pytest.approx(99 / 0.5)
    assert out.spo2_imputation == "spo2_gt_97_no_imputation"


def test_resolver_keeps_raw_sf_when_no_fio2_but_room_air_documented() -> None:
    out = resolve_spo2_fio2_pao2(
        **_args(fio2_fraction=None, fio2_observed_at=None, fio2_evidence_id=None)
    )
    assert out.source is None  # missing O2 documentation is never room air

    out = resolve_spo2_fio2_pao2(
        **_args(
            fio2_fraction=None,
            fio2_observed_at=None,
            fio2_evidence_id=None,
            explicit_room_air=True,
            room_air_evidence_id="roomair/1",
            room_air_observed_at=datetime(2020, 1, 1, 1),
        )
    )
    assert out.source == "spo2"
    assert out.raw_spo2_fio2 == pytest.approx(88 / 0.21)
    assert out.spo2_fio2 is not None
    assert "roomair/1" in out.evidence_ids

    # A room-air statement without evidence or time cannot stand in for FiO2.
    no_time = resolve_spo2_fio2_pao2(
        **_args(
            fio2_fraction=None,
            fio2_observed_at=None,
            fio2_evidence_id=None,
            explicit_room_air=True,
            room_air_evidence_id="roomair/1",
        )
    )
    assert no_time.source is None


def test_resolver_room_air_never_overrides_documented_fio2() -> None:
    out = resolve_spo2_fio2_pao2(
        **_args(explicit_room_air=True, room_air_evidence_id="roomair/1")
    )
    assert out.source == "spo2"
    assert out.raw_spo2_fio2 == pytest.approx(88 / 0.5)
    assert "roomair/1" not in out.evidence_ids


def test_resolver_room_air_evidence_required() -> None:
    out = resolve_spo2_fio2_pao2(
        **_args(
            fio2_fraction=None,
            fio2_observed_at=None,
            fio2_evidence_id=None,
            explicit_room_air=True,
            room_air_evidence_id=None,
        )
    )
    # Explicit room-air flag without evidence is treated as missing documentation.
    assert out.source is None


def test_resolver_stale_spo2_not_paired() -> None:
    out = resolve_spo2_fio2_pao2(
        **_args(
            spo2_observed_at=datetime(2019, 12, 1),
            as_of=datetime(2020, 1, 1, 2),
            lookback=timedelta(hours=24),
        )
    )
    assert out.source is None


# --- preserved pre-imputation cases (expectations updated for the imputation) ---


def _both_args(**overrides):
    values = {
        "pao2_mmhg": 60.0,
        "pao2_observed_at": datetime(2020, 1, 1, 1),
        "pao2_evidence_id": "pao2/1",
        "spo2_percent": 88.0,
        "spo2_observed_at": datetime(2020, 1, 1, 1),
        "spo2_evidence_id": "spo2/1",
        "fio2_fraction": 0.5,
        "fio2_observed_at": datetime(2020, 1, 1, 1),
        "fio2_evidence_id": "fio2/1",
        "as_of": datetime(2020, 1, 1, 2),
    }
    values.update(overrides)
    return values


def test_prefers_pao2_when_both_measurements_pair() -> None:
    out = resolve_spo2_fio2_pao2(**_both_args())
    assert out.source == "pao2"
    assert out.pao2_fio2 == 120.0
    assert out.spo2_fio2 is None
    assert out.raw_spo2_fio2 is None
    assert out.evidence_ids == ("pao2/1", "fio2/1")


def test_falls_back_to_spo2_when_pao2_is_unavailable() -> None:
    out = resolve_spo2_fio2_pao2(**_both_args(pao2_mmhg=None, pao2_observed_at=None))
    assert out.source == "spo2"
    assert out.raw_spo2_fio2 == pytest.approx(176.0)
    assert out.spo2_fio2 == pytest.approx(64 + 0.84 * 176.0)


def test_does_not_infer_ambient_air_or_pair_stale_fio2() -> None:
    no_fio2 = resolve_spo2_fio2_pao2(
        **_both_args(fio2_fraction=None, fio2_observed_at=None, fio2_evidence_id=None)
    )
    stale = resolve_spo2_fio2_pao2(
        **_both_args(
            fio2_observed_at=datetime(2019, 12, 30),
            as_of=datetime(2020, 1, 1, 2),
        )
    )
    assert no_fio2.source is None
    assert stale.source is None


def test_does_not_use_observations_after_availability_clock() -> None:
    out = resolve_spo2_fio2_pao2(
        **_both_args(as_of=datetime(2020, 1, 1), lookback=timedelta(hours=24))
    )
    assert out.source is None
