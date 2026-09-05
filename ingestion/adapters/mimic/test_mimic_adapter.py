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


# --- B1 pressor extraction integration (CURIE-051) ---------------------------


def _pressor_row(**kw) -> dict:
    row = {
        "starttime": "2150-01-01 06:00:00",
        "endtime": "2150-01-01 10:00:00",
        "itemid": 221906,
        "rate": 0.2,
        "rateuom": "mcg/kg/min",
        "ordercategoryname": "01-Drips",
        "statusdescription": "Running",
    }
    row.update(kw)
    return row


def _weight_row(charttime: str, itemid: int = 224639, value: float = 70.0) -> tuple:
    from ingestion.adapters.mimic.timeline import parse_mimic_ts

    return (parse_mimic_ts(charttime), itemid, value)


def test_pressor_at_known_dose_with_contemporaneous_weight() -> None:
    from ingestion.adapters.mimic.extract import _pressor_at

    result = _pressor_at(
        [_pressor_row(rate=5.0, rateuom="mcg/min")],
        weight_rows=[_weight_row("2150-01-01 05:00:00", value=50.0)],
        as_of=datetime(2150, 1, 1, 8, 0, 0),
    )
    assert result.present
    assert result.agent == "norepinephrine"
    assert result.dose == pytest.approx(0.1)
    assert result.evidence_ids == ["MIMIC/inputevents/221906/2150-01-01 06:00:00"]
    assert result.details[0]["known"] is True
    assert result.details[0]["reason"] == "divided_by_weight_kg"


def test_pressor_at_unknown_unit_never_fabricates_dose() -> None:
    from ingestion.adapters.mimic.extract import _pressor_at

    result = _pressor_at(
        [_pressor_row(itemid=222315, rate=3.0, rateuom="units/hour")],
        weight_rows=[_weight_row("2150-01-01 05:00:00")],
        as_of=datetime(2150, 1, 1, 8, 0, 0),
    )
    assert result.present  # pressor present ...
    assert result.dose is None  # ... but dose explicitly unknown
    assert result.agent == "other"
    assert result.details[0]["reason"].startswith("unsupported_unit:")
    assert result.details[0]["source_unit"] == "unsupported:units/hour"


def test_pressor_at_future_only_weight_is_unknown_dose() -> None:
    from ingestion.adapters.mimic.extract import _pressor_at

    result = _pressor_at(
        [_pressor_row(rate=5.0, rateuom="mcg/min")],
        weight_rows=[_weight_row("2150-01-01 09:00:00", value=50.0)],  # after starttime
        as_of=datetime(2150, 1, 1, 8, 0, 0),
    )
    assert result.present
    assert result.dose is None
    assert result.details[0]["weight_status"] == "only_future"


def test_pressor_at_overlapping_agents_prefers_highest_band() -> None:
    from ingestion.adapters.mimic.extract import _pressor_at

    rows = [
        _pressor_row(itemid=221653, rate=5.0, rateuom="mcg/kg/min"),  # dobutamine
        _pressor_row(itemid=221906, rate=0.3, rateuom="mcg/kg/min"),  # norepinephrine
    ]
    result = _pressor_at(rows, weight_rows=[], as_of=datetime(2150, 1, 1, 8, 0, 0))
    assert result.agent == "norepinephrine"
    assert result.dose == 0.3
    # all active rows' evidence preserved for auditability
    assert len(result.evidence_ids) == 2


def test_pressor_at_bolus_present_but_dose_not_applicable() -> None:
    from ingestion.adapters.mimic.extract import _pressor_at

    result = _pressor_at(
        [
            _pressor_row(
                itemid=221749, rate=50.0, rateuom="mg", ordercategoryname="05-Med Bolus"
            )
        ],
        weight_rows=[],
        as_of=datetime(2150, 1, 1, 8, 0, 0),
    )
    assert result.present
    assert result.dose is None
    assert result.details[0]["reason"] == "bolus_order_dose_not_applicable"


def test_pressor_at_inactive_rows_ignored() -> None:
    from ingestion.adapters.mimic.extract import _pressor_at

    result = _pressor_at(
        [_pressor_row(starttime="2150-01-01 06:00:00", endtime="2150-01-01 07:00:00")],
        weight_rows=[],
        as_of=datetime(2150, 1, 1, 8, 0, 0),
    )
    assert not result.present


def test_urine_output_ineligible_before_24h_window() -> None:
    intime = datetime(2150, 1, 1, 0, 0, 0)
    as_of = intime.replace(hour=12)  # only 12h of stay
    output_rows = [{"charttime": "2150-01-01 06:00:00", "itemid": 226559, "value": 400.0}]
    inputs = build_sofa_inputs(
        as_of=as_of,
        lab_rows=[],
        chart_rows=[],
        input_rows=[],
        output_rows=output_rows,
        stay_intime=intime,
    )
    renal = next(i for i in inputs if i.name == SofaComponentName.RENAL)
    assert renal.urine_output_ml_day is None
    # after 24h the same rows form a full-day total
    inputs_after = build_sofa_inputs(
        as_of=intime.replace(day=2),
        lab_rows=[],
        chart_rows=[],
        input_rows=[],
        output_rows=output_rows,
        stay_intime=intime,
    )
    renal_after = next(i for i in inputs_after if i.name == SofaComponentName.RENAL)
    assert renal_after.urine_output_ml_day == 400.0


def test_build_sofa_inputs_returns_pressor_details_on_demand() -> None:
    inputs, details = build_sofa_inputs(
        as_of=datetime(2150, 1, 1, 8, 0, 0),
        lab_rows=[],
        chart_rows=[],
        input_rows=[_pressor_row(rate=5.0, rateuom="mcg/min")],
        output_rows=[],
        weight_rows=[_weight_row("2150-01-01 05:00:00", value=50.0)],
        return_pressor_details=True,
    )
    cv = next(i for i in inputs if i.name == SofaComponentName.CARDIOVASCULAR)
    assert cv.on_vasopressors is True
    assert cv.vasopressor_dose_ug_kg_min == pytest.approx(0.1)
    assert details[0]["weight_kg"] == 50.0
    assert details[0]["evidence_id"].startswith("MIMIC/inputevents/")
