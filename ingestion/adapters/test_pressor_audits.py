"""Tests for the read-only MIMIC + eICU pressor unit audits (plan B1 step 1)."""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

import pytest

from ingestion.adapters.eicu.pressor_audit import (
    _pressor_agent,
    _rate_unit_from_drugname,
    audit_eicu_pressors,
)
from ingestion.adapters.mimic.pressor_audit import audit_inputevents_pressors

DEMO_ROOT = Path("data")


def _write_gz(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(["" if v is None else str(v) for v in row])


def _mimic_inputevents(tmp: Path) -> Path:
    root = tmp / "mimic-audit"
    _write_gz(
        root / "icu" / "inputevents.csv.gz",
        ["itemid", "rate", "rateuom", "patientweight"],
        [
            [221906, "0.1", "mcg/kg/min", "80"],  # known
            [222315, "2", "units/hour", "80"],  # unsupported → unknown
            [221662, "5", "mcg/min", "80"],  # needs weight (has valid) → known
            [221986, "1", "mcg/kg/min", "80"],  # milrinone → not a pressor
            [221906, "", "mcg/kg/min", "80"],  # missing rate
        ],
    )
    return root


def test_mimic_audit_classifies_units(tmp_path: Path) -> None:
    report = audit_inputevents_pressors(_mimic_inputevents(tmp_path))
    assert report["mapped_pressor_rows"] == 4
    assert report["non_pressor_rows"] == 1
    units = report["units"]
    assert units["mcg/kg/min"]["dose_known"] == 1
    assert units["mcg/kg/min"]["dose_unknown"] == 1  # missing rate
    assert units["units/hour"]["dose_unknown"] == 1
    assert units["mcg/min"]["dose_known"] == 1
    assert report["status"] == "AUDIT_ONLY_NOT_FROZEN"


def _eicu_infusiondrug(tmp: Path) -> Path:
    root = tmp / "eicu-audit"
    _write_gz(
        root / "infusiondrug.csv.gz",
        ["drugname", "drugrate", "patientweight"],
        [
            ["Norepinephrine (mcg/kg/min)", "0.2", "70"],  # known
            ["Norepinephrine (ml/hr)", "10", "70"],  # volume → unknown
            ["Vasopressin (units/min)", "0.04", "70"],  # unsupported → unknown
            ["Furosemide (mg/hr)", "10", "70"],  # not a pressor
            ["Dopamine (mcg/min)", "400", "70"],  # weight-needed, present → known
            ["Dopamine (mcg/min)", "400", ""],  # weight missing → unknown
        ],
    )
    return root


def test_eicu_agent_and_unit_parsing() -> None:
    assert _pressor_agent("Norepinephrine (ml/hr)") == "norepinephrine"
    assert _pressor_agent("Vasopressin (units/min)") == "other"
    assert _pressor_agent("Furosemide (mg/hr)") is None
    assert _rate_unit_from_drugname("Norepinephrine (mcg/kg/min)") == "mcg/kg/min"
    assert _rate_unit_from_drugname("Norepinephrine") == ""


def test_eicu_audit_classifies_units(tmp_path: Path) -> None:
    report = audit_eicu_pressors(_eicu_infusiondrug(tmp_path))
    assert report["mapped_pressor_rows"] == 5
    assert report["non_pressor_rows"] == 1
    units = report["units"]
    assert units["mcg/kg/min"]["dose_known"] == 1
    assert units["ml/hr"]["unknown:volume_rate_without_concentration"] == 1
    assert units["units/min"]["unknown:unsupported_unit:units/min"] == 1
    assert units["mcg/min"]["dose_known"] == 1
    assert units["mcg/min"]["unknown:weight_unavailable_or_only_future"] == 1


@pytest.mark.integration
def test_mimic_audit_runs_on_open_demo() -> None:
    root = DEMO_ROOT / "mimic-iv-demo"
    if not (root / "icu" / "inputevents.csv.gz").is_file():
        pytest.skip("demo data missing")
    report = audit_inputevents_pressors(root)
    assert report["mapped_pressor_rows"] > 0
    assert report["status"] == "AUDIT_ONLY_NOT_FROZEN"


@pytest.mark.integration
def test_eicu_audit_runs_on_open_demo() -> None:
    root = DEMO_ROOT / "eicu-crd-demo"
    if not (root / "infusiondrug.csv.gz").is_file():
        pytest.skip("demo data missing")
    report = audit_eicu_pressors(root)
    assert report["mapped_pressor_rows"] > 0
    assert report["status"] == "AUDIT_ONLY_NOT_FROZEN"
