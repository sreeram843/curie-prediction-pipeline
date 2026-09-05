"""Tests for the MIMIC completeness audit (Phase A scaffolding)."""

from __future__ import annotations

import gzip
from pathlib import Path

from eval.mimic_study.completeness_audit import (
    _sharded_replay,
    reconcile_loader_vs_direct,
    stream_stats,
)


def _write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(text)


def _make_root(tmp: Path) -> Path:
    root = tmp / "mimic"
    _write_gz(
        root / "icu" / "icustays.csv.gz",
        "subject_id,hadm_id,stay_id,intime,outtime\n"
        "1,10,100,2150-01-01 00:00:00,2150-01-02 00:00:00\n"
        "2,20,200,2150-01-01 00:00:00,2150-01-02 00:00:00\n",
    )
    _write_gz(
        root / "hosp" / "labevents.csv.gz",
        "subject_id,hadm_id,itemid,charttime,valuenum\n"
        "1,10,50912,2150-01-01 01:00:00,1.2\n"
        "1,10,51265,2150-01-01 01:00:00,200\n"
        "1,10,50885,2150-01-01 01:00:00,0.9\n"
        "1,10,50821,2150-01-01 01:00:00,90\n"
        "2,20,50912,2150-01-01 01:00:00,1.5\n",
    )
    _write_gz(
        root / "icu" / "chartevents.csv.gz",
        "stay_id,charttime,itemid,valuenum\n"
        "100,2150-01-01 02:00:00,220052,75\n"
        "100,2150-01-01 02:00:00,220277,97\n"
        "100,2150-01-01 02:00:00,223835,50\n"
        "100,2150-01-01 02:00:00,220739,4\n"
        "100,2150-01-01 02:00:00,223900,5\n"
        "100,2150-01-01 02:00:00,223901,6\n"
        "200,2150-01-01 02:00:00,220052,80\n",
    )
    _write_gz(
        root / "icu" / "inputevents.csv.gz",
        "stay_id,starttime,endtime,itemid,rate,rateuom,patientweight\n"
        "100,2150-01-01 03:00:00,2150-01-01 04:00:00,221906,0.1,mcg/kg/min,\n"
        "200,2150-01-01 03:00:00,2150-01-01 04:00:00,221906,10,mL/hour,70\n",
    )
    _write_gz(
        root / "icu" / "outputevents.csv.gz",
        "stay_id,charttime,itemid,value\n"
        "100,2150-01-01 10:00:00,226559,300\n",
    )
    return root


_STAYS = [
    {
        "stay_id": "100",
        "subject_id": "1",
        "hadm_id": "10",
        "intime": "2150-01-01 00:00:00",
        "outtime": "2150-01-02 00:00:00",
    },
    {
        "stay_id": "200",
        "subject_id": "2",
        "hadm_id": "20",
        "intime": "2150-01-01 00:00:00",
        "outtime": "2150-01-02 00:00:00",
    },
]


def test_stream_stats_covers_components(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    out = stream_stats(root, _STAYS)
    assert out["stays_in_audit"] == 2
    comps = out["components"]
    assert comps["cns_gcs"]["stays_with_observation"] == 1
    assert comps["cns_gcs"]["stays_with_first_day_observation"] == 1
    assert comps["respiration_fio2"]["observation_rate"] == 0.5
    assert comps["cardiovascular_pressor"]["stays_with_observation"] == 2
    assert comps["renal_creatinine"]["stays_with_observation"] == 2
    assert comps["renal_urine_output"]["stays_with_observation"] == 1
    assert out["gcs_all_three_subscales_present_stays"] == 1
    dose = out["pressor_dose"]
    assert dose["classification"]["known"] == 1
    assert dose["classification"]["unknown"] == 1
    assert "reason:volume_rate_without_concentration" in dose["classification"]
    assert out["runtime"]["stream_seconds"] >= 0


def test_stream_stats_limits_rows(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    out = stream_stats(root, _STAYS, limit_rows=3)
    assert out["stays_in_audit"] == 2
    assert out["pressor_dose"]["classification"].get("known", 0) <= 1


def test_sharded_replay_produces_completeness(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    out = _sharded_replay(
        root, _STAYS, limit=2, seed=42, batch_size=1
    )
    assert out["sample"]["scored_stays"] == 2
    assert out["completeness"]
    assert set(out["components"].keys()) == {
        "respiration",
        "coagulation",
        "liver",
        "cardiovascular",
        "cns",
        "renal",
    }
    assert out["status"] == "AUDIT_ONLY_NOT_FROZEN"


def test_reconcile_loader_vs_direct_matches(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    out = reconcile_loader_vs_direct(root, _STAYS, n_stays=2)
    for table in ("chartevents", "labevents"):
        t = out["tables"][table]
        assert t["match"] is True
        assert t["direct_rows"] == t["loader_rows"]
        assert t["missing_from_loader"] == 0
        assert t["extra_in_loader"] == 0
