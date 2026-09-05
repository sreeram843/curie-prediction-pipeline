"""Tests for the reproducible stay-level source index (Phase C1).

These tests build tiny synthetic MIMIC-IV-shaped / eICU-shaped source trees and
verify: row-level source/index equality, deterministic rebuilds, bounded ==
full row extraction, timestamp-failure accounting, poisoning behavior,
ordering, and validation failure modes.
"""

from __future__ import annotations

import csv
import gzip
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

pyarrow = pytest.importorskip("pyarrow")  # noqa: F841 — [study] extra

from eval.mimic_study.indexing import (  # noqa: E402
    EICU_EPOCH,
    IndexError,
    build_index,
    compute_index_hash,
    load_stay_events,
    load_stays,
    reconcile_source_to_index,
    scan_index_events,
    validate_index,
)


def _write_gz(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(["" if v is None else str(v) for v in row])


def make_mimic_source(tmp: Path) -> Path:
    """Small synthetic MIMIC-IV tree: 3 stays, 2 subjects."""
    root = tmp / "mimic-src"
    _write_gz(
        root / "icu" / "icustays.csv.gz",
        ["subject_id", "hadm_id", "stay_id", "intime", "outtime"],
        [
            [101, 1001, 10, "2020-01-01 08:00:00", "2020-01-03 08:00:00"],
            [101, 1002, 11, "2020-02-01 08:00:00", "2020-02-03 08:00:00"],
            [102, 1003, 12, "2020-03-01 08:00:00", "2020-03-03 08:00:00"],
        ],
    )
    _write_gz(
        root / "hosp" / "patients.csv.gz",
        ["subject_id", "gender", "anchor_age"],
        [[101, "F", 62], [102, "M", 40]],
    )
    _write_gz(
        root / "hosp" / "admissions.csv.gz",
        ["hadm_id", "subject_id", "admittime", "dischtime"],
        [
            [1001, 101, "2020-01-01 07:00:00", "2020-01-05 09:00:00"],
            [1002, 101, "2020-02-01 07:00:00", "2020-02-06 09:00:00"],
            [1003, 102, "2020-03-01 07:00:00", "2020-03-04 09:00:00"],
        ],
    )
    _write_gz(
        root / "hosp" / "labevents.csv.gz",
        [
            "subject_id", "hadm_id", "itemid", "charttime", "storetime", "value", "valuenum",
            "valueuom",
        ],
        [
            # creatinine for stay 10 (storetime after charttime)
            [101, 1001, 50912, "2020-01-01 10:00:00", "2020-01-01 11:00:00", "1.2", "1.2", "mg/dL"],
            # creatinine correction for stay 10, available 2h later
            [101, 1001, 50912, "2020-01-01 10:00:00", "2020-01-01 13:00:00", "2.9", "2.9", "mg/dL"],
            # platelets stay 11
            [101, 1002, 51265, "2020-02-01 10:00:00", "2020-02-01 10:00:00", "180", "180", "K/uL"],
            # pao2 stay 12
            [102, 1003, 50821, "2020-03-01 10:00:00", "2020-03-01 10:00:00", "88", "88", "mmHg"],
            # bad timestamp → excluded + counted
            [102, 1003, 50885, "not-a-time", "", "2", "2", "mg/dL"],
            # unmapped itemid → filtered out (mapped build)
            [102, 1003, 99999, "2020-03-01 10:00:00", "", "x", "1", "mg/dL"],
            # empty hadm on single-stay subject → assigned via subject
            [102, "", 50912, "2020-03-01 12:00:00", "2020-03-01 12:00:00", "0.9", "0.9", "mg/dL"],
        ],
    )
    _write_gz(
        root / "icu" / "chartevents.csv.gz",
        [
            "subject_id", "hadm_id", "stay_id", "itemid", "charttime", "value", "valuenum",
            "valueuom",
        ],
        [
            [101, 1001, 10, 220052, "2020-01-01 09:00:00", "75", "75", "mmHg"],
            [101, 1001, 10, 220052, "2020-01-01 10:00:00", "61", "61", "mmHg"],
            [101, 1001, 10, 220277, "2020-01-01 10:00:00", "96", "96", "%"],
            # text value with non-numeric valuenum → kept raw, value_num None
            [101, 1001, 10, 220277, "2020-01-01 11:00:00", "normal", "", "%"],
            [102, 1003, 12, 223900, "2020-03-01 10:00:00", "5", "5", ""],
            # unknown stay → unassigned
            [102, 1003, 99999, 220052, "2020-03-01 10:00:00", "70", "70", "mmHg"],
        ],
    )
    _write_gz(
        root / "icu" / "inputevents.csv.gz",
        [
            "subject_id", "hadm_id", "stay_id", "itemid", "starttime", "endtime", "rate",
            "rateuom", "amount", "amountuom",
        ],
        [
            [
                101, 1001, 10, 221906, "2020-01-01 09:30:00", "2020-01-01 12:00:00", "0.3",
                "mcg/kg/min", "10", "mL",
            ],
            [
                101, 1001, 10, 221662, "2020-01-01 10:00:00", "2020-01-01 12:00:00", "5",
                "mcg/kg/min", "20", "mL",
            ],
        ],
    )
    _write_gz(
        root / "icu" / "outputevents.csv.gz",
        ["subject_id", "hadm_id", "stay_id", "itemid", "charttime", "value", "valueuom"],
        [[101, 1001, 10, 226559, "2020-01-01 12:00:00", "250", "mL"]],
    )
    _write_gz(
        root / "hosp" / "diagnoses_icd.csv.gz",
        ["subject_id", "hadm_id", "icd_code", "icd_version", "long_title"],
        [
            [101, 1001, "A419", "10", "Sepsis"],
            [102, 1003, "J9600", "10", "Acute respiratory failure"],
        ],
    )
    return root


def make_eicu_source(tmp: Path) -> Path:
    """Small synthetic eICU tree: 2 unit stays."""
    root = tmp / "eicu-src"
    _write_gz(
        root / "patient.csv.gz",
        [
            "patientunitstayid",
            "uniquepid",
            "patienthealthsystemstayid",
            "gender",
            "age",
            "unitdischargeoffset",
        ],
        [
            [7001, "u-1", "h-1", "Female", "60", "2880"],
            [7002, "u-2", "h-2", "Male", "55", "1500"],
        ],
    )
    _write_gz(
        root / "lab.csv.gz",
        ["patientunitstayid", "labname", "labresult", "labresultoffset", "labmeasurenamesystem"],
        [
            [7001, "creatinine", "1.3", "120", "mg/dL"],
            [7001, "platelets x 1000", "150", "130", "K/uL"],
            [7001, "something else", "9", "140", "mg/dL"],
            [7002, "creatinine", "0.8", "60", "mg/dL"],
        ],
    )
    _write_gz(
        root / "vitalPeriodic.csv.gz",
        ["patientunitstayid", "observationoffset", "sao2", "systemicmean"],
        [[7001, "60", "95", "72"], [7002, "60", "99", "80"]],
    )
    _write_gz(
        root / "vitalAperiodic.csv.gz",
        ["patientunitstayid", "observationoffset", "noninvasivemean"],
        [[7001, "90", "65"]],
    )
    _write_gz(
        root / "nurseCharting.csv.gz",
        [
            "patientunitstayid",
            "nursingchartoffset",
            "nursingchartcelltypevallabel",
            "nursingchartcelltypevalname",
            "nursingchartvalue",
        ],
        [[7001, "100", "GCS Total", "Value", "14"], [7001, "120", "O2 Saturation", "", "97"]],
    )
    _write_gz(
        root / "respiratoryCharting.csv.gz",
        ["patientunitstayid", "respchartoffset", "respchartvaluelabel", "respchartvalue"],
        [[7001, "110", "FiO2", "40"]],
    )
    _write_gz(
        root / "intakeOutput.csv.gz",
        ["patientunitstayid", "intakeoutputoffset", "celllabel", "cellvaluenumeric"],
        [[7001, "200", "Urine", "300"]],
    )
    _write_gz(
        root / "infusionDrug.csv.gz",
        ["patientunitstayid", "infusionoffset", "drugname", "drugrate", "patientweight"],
        [[7001, "150", "Norepinephrine (mcg/kg/min)", "0.25", "80"]],
    )
    _write_gz(
        root / "physicalExam.csv.gz",
        ["patientunitstayid", "physicalexamoffset", "physicalexampath", "physicalexamvalue"],
        [[7001, "130", "notes/Physical Exam/Neurologic/GCS/eyes score/4", ""]],
    )
    _write_gz(
        root / "diagnosis.csv.gz",
        ["patientunitstayid", "diagnosisoffset", "icd9code", "diagnosisstring"],
        [[7001, "100", "995.91", "sepsis"]],
    )
    return root


@pytest.fixture(scope="module")
def mimic_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_mimic_source(tmp_path_factory.mktemp("mimic-fixture"))


@pytest.fixture(scope="module")
def eicu_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_eicu_source(tmp_path_factory.mktemp("eicu-fixture"))


def _build(tmp: Path, source: Path, **kwargs: Any) -> tuple[dict[str, Any], Path]:
    index_dir = tmp / "idx"
    meta = build_index(source_root=source, index_dir=index_dir, **kwargs)
    return meta, index_dir


class TestMimicIndex:
    def test_build_validate_reconcile(self, mimic_source: Path, tmp_path: Path) -> None:
        meta, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        assert meta["stays"]["total"] == 3
        assert meta["events"]["total"] > 0
        assert validate_index(index_dir)["ok"]
        report = reconcile_source_to_index(
            source_root=mimic_source, index_dir=index_dir, dataset="mimic", limit=3
        )
        assert report["ok"], report["mismatches"]
        assert report["rows_compared"] == meta["events"]["total"]

    def test_deterministic_rebuild(self, mimic_source: Path, tmp_path: Path) -> None:
        meta_a, dir_a = _build(tmp_path, mimic_source, dataset="mimic")
        meta_b, dir_b = _build(tmp_path / "b", mimic_source, dataset="mimic")
        assert meta_a["index_hash"] == meta_b["index_hash"]
        assert compute_index_hash(dir_a) == compute_index_hash(dir_b)

    def test_bounded_extraction_matches_full_rows(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        _, full = _build(tmp_path, mimic_source, dataset="mimic")
        _, bounded = _build(tmp_path / "b", mimic_source, dataset="mimic", limit=2)
        for stay in load_stays(full)[:2]:
            full_rows = load_stay_events(full, str(stay["stay_id"]))
            bounded_rows = load_stay_events(bounded, str(stay["stay_id"]))
            assert [r["source_row"] for r in full_rows] == [
                r["source_row"] for r in bounded_rows
            ]

    def test_ordering_within_partition(self, mimic_source: Path, tmp_path: Path) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        for stay in load_stays(index_dir):
            rows = load_stay_events(index_dir, str(stay["stay_id"]))
            keys = [
                (r["availability_time"], r["event_time"], r["source_table"], r["source_row"])
                for r in rows
            ]
            assert keys == sorted(keys)

    def test_timestamp_failures_counted_and_excluded(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        meta, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        lab_meta = meta["source_files"]["hosp/labevents.csv.gz"]
        assert lab_meta["timestamp_failures"] == 1  # "not-a-time"
        all_rows = []
        for stay in load_stays(index_dir):
            all_rows.extend(load_stay_events(index_dir, str(stay["stay_id"])))
        assert all("not-a-time" not in str(r["value_raw"]) for r in all_rows)

    def test_unassigned_rows_counted(self, mimic_source: Path, tmp_path: Path) -> None:
        meta, _ = _build(tmp_path, mimic_source, dataset="mimic")
        chart_meta = meta["source_files"]["icu/chartevents.csv.gz"]
        assert chart_meta["unassigned_rows"] == 1  # unknown stay 99999

    def test_non_numeric_value_raw_preserved(self, mimic_source: Path, tmp_path: Path) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        rows = load_stay_events(index_dir, "10")
        text_row = [r for r in rows if r["value_raw"] == "normal"]
        assert len(text_row) == 1
        assert text_row[0]["value_num"] is None
        assert text_row[0]["itemid_num"] == 220277

    def test_diagnosis_availability_is_discharge_time(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        dx = [r for r in load_stay_events(index_dir, "10") if r["event_family"] == "diagnosis"]
        assert dx and all(r["is_discharge_diagnosis"] for r in dx)
        assert all(
            r["availability_time"] == datetime(2020, 1, 5, 9, 0, 0) for r in dx
        )

    def test_lab_availability_is_max_of_chart_and_store(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        rows = load_stay_events(index_dir, "10")
        cr = [r for r in rows if r["event_family"] == "lab" and r["itemid_num"] == 50912]
        by_value = {r["value_raw"]: r for r in cr}
        assert by_value["1.2"]["availability_time"] == datetime(2020, 1, 1, 11, 0, 0)
        assert by_value["2.9"]["availability_time"] == datetime(2020, 1, 1, 13, 0, 0)

    def test_source_row_identity_and_evidence_id(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        rows = load_stay_events(index_dir, "10")
        evidence_ids = [r["evidence_id"] for r in rows]
        assert len(set(evidence_ids)) == len(rows)  # unique per source row
        for row in rows:
            assert row["evidence_id"] == f"mimic/{row['source_table']}/{row['source_row']}"
            assert row["extra_json"]  # full source-row provenance retained

    def test_scan_with_predicate_pushdown(self, mimic_source: Path, tmp_path: Path) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        table = scan_index_events(index_dir, stay_ids=["10"])
        assert table is not None and table.num_rows == len(load_stay_events(index_dir, "10"))
        filtered = scan_index_events(
            index_dir, stay_ids=["10", "11"], filters=[("itemid_num", "==", 50912)]
        )
        assert all(int(r["itemid_num"]) == 50912 for r in filtered.to_pylist())

    def test_existing_index_requires_force(self, mimic_source: Path, tmp_path: Path) -> None:
        _build(tmp_path, mimic_source, dataset="mimic")
        with pytest.raises(IndexError, match="force"):
            build_index(source_root=mimic_source, index_dir=tmp_path / "idx", dataset="mimic")
        build_index(
            source_root=mimic_source, index_dir=tmp_path / "idx", dataset="mimic", force=True
        )

    def test_poisoned_gzip_fails_closed(self, mimic_source: Path, tmp_path: Path) -> None:
        root = tmp_path / "poison"
        shutil.copytree(mimic_source, root)
        chart = root / "icu" / "chartevents.csv.gz"
        raw = bytearray(chart.read_bytes())
        for i in range(20, min(80, len(raw))):
            raw[i] = 0xFF
        chart.write_bytes(bytes(raw))
        with pytest.raises(IndexError, match="chartevents"):
            build_index(source_root=root, index_dir=tmp_path / "idx", dataset="mimic")
        assert not (tmp_path / "idx").exists()

    def test_missing_scope_column_is_unassigned(self, tmp_path: Path) -> None:
        root = tmp_path / "missing-col"
        _write_gz(
            root / "icu" / "icustays.csv.gz",
            ["subject_id", "hadm_id", "stay_id", "intime", "outtime"],
            [[1, 1, 1, "2020-01-01 08:00:00", "2020-01-02 08:00:00"]],
        )
        _write_gz(
            root / "hosp" / "patients.csv.gz",
            ["subject_id", "anchor_age"],
            [[1, 40]],
        )
        _write_gz(
            root / "hosp" / "admissions.csv.gz",
            ["hadm_id", "dischtime"],
            [[1, "2020-01-03 08:00:00"]],
        )
        _write_gz(
            root / "icu" / "chartevents.csv.gz",
            ["subject_id", "hadm_id", "itemid", "charttime", "valuenum"],
            [[1, 1, 220052, "2020-01-01 09:00:00", "70"]],
        )
        _write_gz(
            root / "hosp" / "labevents.csv.gz",
            ["subject_id", "hadm_id", "itemid", "charttime", "valuenum"],
            [[1, 999, 50912, "2020-01-01 09:00:00", "1.0"]],
        )
        _write_gz(
            root / "icu" / "inputevents.csv.gz",
            ["subject_id", "hadm_id", "itemid", "starttime", "rate"],
            [[1, 1, 221906, "2020-01-01 09:00:00", "0.1"]],
        )
        _write_gz(
            root / "icu" / "outputevents.csv.gz",
            ["subject_id", "hadm_id", "itemid", "charttime", "value"],
            [[1, 1, 226559, "2020-01-01 09:00:00", "100"]],
        )
        _write_gz(
            root / "hosp" / "diagnoses_icd.csv.gz",
            ["subject_id", "hadm_id", "icd_code", "long_title"],
            [[1, 999, "A419", "Sepsis"]],
        )
        meta, _ = _build(tmp_path, root, dataset="mimic")
        # rows without a resolvable stay scope are counted unassigned, no crash
        assert all(
            info["unassigned_rows"] > 0
            for rel, info in meta["source_files"].items()
            if rel.endswith(
                (
                    "chartevents.csv.gz",
                    "labevents.csv.gz",
                    "inputevents.csv.gz",
                    "outputevents.csv.gz",
                    "diagnoses_icd.csv.gz",
                )
            )
        )

    def test_validator_detects_deleted_partition(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        shutil.rmtree(index_dir / "events" / "stay_id=10")
        report = validate_index(index_dir)
        assert not report["ok"]
        assert "stay_partition_coverage" in report["failures"]

    def test_validator_detects_row_tampering(
        self, mimic_source: Path, tmp_path: Path
    ) -> None:
        _, index_dir = _build(tmp_path, mimic_source, dataset="mimic")
        part = index_dir / "events" / "stay_id=10" / "part-0.parquet"
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pq.read_table(part)
        values = table["value_num"].to_pylist()
        values[0] = 9999.0 if values[0] is not None else None
        col_idx = table.schema.get_field_index("value_num")
        pq.write_table(table.set_column(col_idx, "value_num", pa.array(values)), part)
        report = validate_index(index_dir)
        assert not report["ok"]
        assert "index_hash" in report["failures"]


class TestEicuIndex:
    def test_build_validate_reconcile(self, eicu_source: Path, tmp_path: Path) -> None:
        meta, index_dir = _build(tmp_path, eicu_source, dataset="eicu")
        assert meta["stays"]["total"] == 2
        assert validate_index(index_dir)["ok"]
        report = reconcile_source_to_index(
            source_root=eicu_source, index_dir=index_dir, dataset="eicu", limit=2
        )
        assert report["ok"], report["mismatches"]
        assert report["rows_compared"] == meta["events"]["total"]

    def test_eicu_timestamps_are_epoch_offsets(
        self, eicu_source: Path, tmp_path: Path
    ) -> None:
        _, index_dir = _build(tmp_path, eicu_source, dataset="eicu")
        rows = load_stay_events(index_dir, "7001")
        assert rows
        for row in rows:
            assert row["event_time"] >= EICU_EPOCH
            assert row["availability_time"] == row["event_time"]

    def test_eicu_mapped_filter_excludes_unmapped_labs(
        self, eicu_source: Path, tmp_path: Path
    ) -> None:
        meta, index_dir = _build(tmp_path, eicu_source, dataset="eicu")
        rows = load_stay_events(index_dir, "7001")
        lab_names = {r["itemid"] for r in rows if r["event_family"] == "lab"}
        assert "something else" not in lab_names
        assert {"creatinine", "platelets x 1000"} <= lab_names
        assert meta["source_files"]["lab.csv.gz"]["rows_selected"] == 3
