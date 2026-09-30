"""Tests for ICD sepsis pin loading and matching."""

from __future__ import annotations

import gzip
from pathlib import Path

from eval.mimic_study.icd_sepsis import (
    annotate_icd_sepsis_positive,
    code_matches_sepsis,
    load_icd_sepsis_hadm_ids,
    load_icd_sepsis_pin,
)


def test_frozen_pin_matches_canonical_sepsis_codes() -> None:
    pin = load_icd_sepsis_pin()
    assert code_matches_sepsis("A41.9", pin)
    assert code_matches_sepsis("a419", pin)
    assert code_matches_sepsis("0389", pin)
    assert code_matches_sepsis("995.91", pin)
    assert code_matches_sepsis("R65.21", pin)
    assert not code_matches_sepsis("I10", pin)
    assert not code_matches_sepsis("Z515", pin)


def test_load_icd_sepsis_hadm_ids_from_diagnoses(tmp_path: Path) -> None:
    root = tmp_path
    (root / "hosp").mkdir()
    path = root / "hosp" / "diagnoses_icd.csv.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("subject_id,hadm_id,icd_code,icd_version\n")
        handle.write("1,100,A419,10\n")
        handle.write("1,100,I10,10\n")
        handle.write("2,200,Z515,10\n")
        handle.write("3,300,99591,9\n")
    positives = load_icd_sepsis_hadm_ids(root)
    assert positives == {"100", "300"}


def test_annotate_icd_sepsis_positive_joins_hadm_map() -> None:
    rows = [
        {"stay_id": "s1", "labels": {}},
        {"stay_id": "s2", "hadm_id": "200", "labels": {}},
    ]
    out = annotate_icd_sepsis_positive(
        rows,
        icd_positive_hadm_ids={"100", "200"},
        hadm_by_stay={"s1": "100"},
    )
    assert out[0]["icd_sepsis_positive"] is True
    assert out[0]["hadm_id"] == "100"
    assert out[1]["icd_sepsis_positive"] is True
