"""MIMIC demo path + extract unit tests (no full CSV scan required)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from eval.aki.scoring import compute_aki_score
from eval.sofa.scoring import SofaComponentName, compute_sofa_score
from ingestion.adapters.mimic.extract import build_aki_input, build_sofa_inputs
from ingestion.adapters.mimic.paths import mimic_demo_dir, require_mimic_demo_dir


def test_default_mimic_demo_path_points_under_data() -> None:
    path = mimic_demo_dir()
    assert path.name == "mimic-iv-demo"
    assert path.parent.name == "data"


def test_require_mimic_demo_dir_when_present() -> None:
    root = mimic_demo_dir()
    if not (root / "hosp").is_dir():
        pytest.skip("MIMIC demo not installed locally")
    assert require_mimic_demo_dir() == root.resolve()


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
