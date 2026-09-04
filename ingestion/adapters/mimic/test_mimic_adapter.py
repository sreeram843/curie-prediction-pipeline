"""MIMIC demo path + extract unit tests (no full CSV scan required)."""

from __future__ import annotations

import gzip
from datetime import datetime
from pathlib import Path

import pytest

from eval.aki.scoring import compute_aki_score
from eval.sofa.scoring import SofaComponentName, compute_sofa_score
from ingestion.adapters.mimic.extract import build_aki_input, build_sofa_inputs
from ingestion.adapters.mimic.paths import (
    mimic_demo_dir,
    mimic_dir,
    require_mimic_demo_dir,
    require_mimic_dir,
)


def test_default_mimic_demo_path_points_under_data() -> None:
    path = mimic_demo_dir()
    assert path.name == "mimic-iv-demo"
    assert path.parent.name == "data"


def test_require_mimic_demo_dir_when_present() -> None:
    root = mimic_demo_dir()
    if not (root / "hosp").is_dir():
        pytest.skip("MIMIC demo not installed locally")
    assert require_mimic_demo_dir() == root.resolve()


def _touch_mimic_iv_tables(root: Path) -> None:
    (root / "hosp").mkdir(parents=True)
    (root / "icu").mkdir(parents=True)
    (root / "hosp" / "labevents.csv.gz").write_bytes(b"")
    (root / "icu" / "icustays.csv.gz").write_bytes(b"")


def test_default_mimic_dir_points_under_data() -> None:
    path = mimic_dir()
    assert path.name == "mimic-iv"
    assert path.parent.name == "data"


def test_require_mimic_dir_uses_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _touch_mimic_iv_tables(tmp_path)
    monkeypatch.setenv("CURIE_MIMIC_DIR", str(tmp_path))
    assert require_mimic_dir() == tmp_path.resolve()


def test_require_mimic_dir_resolves_wget_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = tmp_path / "physionet.org" / "files" / "mimiciv" / "3.1"
    _touch_mimic_iv_tables(nested)
    monkeypatch.setenv("CURIE_MIMIC_DIR", str(tmp_path))
    assert require_mimic_dir() == nested.resolve()


def test_require_mimic_dir_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURIE_MIMIC_DIR", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError, match="CURIE_MIMIC_DIR"):
        require_mimic_dir()


def test_require_mimic_dir_falls_back_to_physionet_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CURIE_MIMIC_DIR", raising=False)
    monkeypatch.delenv("MIMIC_DIR", raising=False)
    nested = tmp_path / "physionet.org" / "files" / "mimiciv" / "3.1"
    _touch_mimic_iv_tables(nested)
    monkeypatch.setenv("PHYSIONET_DATA_ROOT", str(tmp_path))
    assert require_mimic_dir() == nested.resolve()


def test_extract_sofa_and_aki_from_synthetic_rows() -> None:
    as_of = datetime(2150, 1, 2, 12, 0, 0)
    lab_rows = [
        {
            "hadm_id": "1",
            "charttime": "2150-01-01 08:00:00",
            "itemid": 50912,
            "valuenum": 1.0,
        },
        {
            "hadm_id": "1",
            "charttime": "2150-01-02 10:00:00",
            "itemid": 50912,
            "valuenum": 2.2,
        },
        {
            "hadm_id": "1",
            "charttime": "2150-01-02 10:00:00",
            "itemid": 51265,
            "valuenum": 40.0,
        },
        {
            "hadm_id": "1",
            "charttime": "2150-01-02 10:00:00",
            "itemid": 50885,
            "valuenum": 2.5,
        },
    ]
    chart_rows = [
        {"charttime": "2150-01-02 11:00:00", "itemid": 220052, "valuenum": 65.0},
        {"charttime": "2150-01-02 11:00:00", "itemid": 220739, "valuenum": 4.0},
        {"charttime": "2150-01-02 11:00:00", "itemid": 223900, "valuenum": 5.0},
        {"charttime": "2150-01-02 11:00:00", "itemid": 223901, "valuenum": 6.0},
    ]
    sofa_inputs = build_sofa_inputs(
        as_of=as_of,
        lab_rows=lab_rows,
        chart_rows=chart_rows,
        input_rows=[],
        output_rows=[],
    )
    by_name = {i.name: i for i in sofa_inputs}
    assert by_name[SofaComponentName.COAGULATION].platelets_10e9_l == 40.0
    assert by_name[SofaComponentName.CNS].gcs == 15
    sofa = compute_sofa_score(
        patient_id="Patient/x",
        event_time=as_of,
        inputs=sofa_inputs,
        rule_bundle_id="sepsis-sofa",
        rule_version="0.2.0",
    )
    assert sofa.total_score is not None
    assert sofa.total_score >= 5

    aki_in = build_aki_input(as_of=as_of, lab_rows=lab_rows, chart_rows=[])
    aki = compute_aki_score(
        patient_id="Patient/x",
        event_time=as_of,
        inputs=aki_in,
        rule_bundle_id="aki-kdigo",
        rule_version="0.2.0",
    )
    assert aki.stage == 2


@pytest.mark.integration
def test_mimic_demo_end_to_end_smoke() -> None:
    root = mimic_demo_dir()
    if not (root / "icu" / "icustays.csv.gz").is_file():
        pytest.skip("MIMIC demo not installed locally")
    from eval.mimic_demo.runner import run_mimic_demo

    report = run_mimic_demo(limit=5)
    assert report["stays_scored"] == 5
    assert Path(report["source"]).exists()


def _write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(text)


def test_run_mimic_full_scores_tiny_dump(tmp_path: Path) -> None:
    from eval.mimic_demo.runner import run_mimic_demo

    _write_gz(
        tmp_path / "icu" / "icustays.csv.gz",
        "subject_id,hadm_id,stay_id,first_careunit,last_careunit,intime,outtime,los\n"
        "1,10,100,MICU,MICU,2150-01-01 00:00:00,2150-01-03 00:00:00,2.0\n",
    )
    _write_gz(
        tmp_path / "hosp" / "labevents.csv.gz",
        "subject_id,hadm_id,charttime,itemid,valuenum\n",
    )
    _write_gz(
        tmp_path / "icu" / "chartevents.csv.gz",
        "stay_id,charttime,itemid,valuenum\n",
    )
    _write_gz(
        tmp_path / "icu" / "inputevents.csv.gz",
        "stay_id,starttime,endtime,itemid,rate,rateuom\n",
    )
    _write_gz(
        tmp_path / "icu" / "outputevents.csv.gz",
        "stay_id,charttime,itemid,value\n",
    )
    report = run_mimic_demo(limit=1, root=tmp_path, dataset="mimic-iv-3.1")
    assert report["dataset"] == "mimic-iv-3.1"
    assert report["stays_scored"] == 1
    assert Path(report["source"]) == tmp_path.resolve()
