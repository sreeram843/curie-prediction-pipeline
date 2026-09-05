from datetime import datetime, timedelta

from ingestion.adapters.respiration import resolve_spo2_fio2_pao2


def _args(**overrides):
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
    out = resolve_spo2_fio2_pao2(**_args())
    assert out.source == "pao2"
    assert out.pao2_fio2 == 120.0
    assert out.spo2_fio2 is None
    assert out.evidence_ids == ("pao2/1", "fio2/1")


def test_falls_back_to_spo2_when_pao2_is_unavailable() -> None:
    out = resolve_spo2_fio2_pao2(**_args(pao2_mmhg=None, pao2_observed_at=None))
    assert out.source == "spo2"
    assert out.spo2_fio2 == 176.0


def test_does_not_infer_ambient_air_or_pair_stale_fio2() -> None:
    no_fio2 = resolve_spo2_fio2_pao2(**_args(fio2_fraction=None))
    stale = resolve_spo2_fio2_pao2(
        **_args(fio2_observed_at=datetime(2019, 12, 30), as_of=datetime(2020, 1, 1, 2))
    )
    assert no_fio2.source is None
    assert stale.source is None


def test_does_not_use_observations_after_availability_clock() -> None:
    out = resolve_spo2_fio2_pao2(
        **_args(as_of=datetime(2020, 1, 1), lookback=timedelta(hours=24))
    )
    assert out.source is None
