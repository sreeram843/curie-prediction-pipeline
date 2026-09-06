"""Tests for the pinned mimic-code label references (Phase C3 pinning, kept
separate from feature replay)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from eval.mimic_study.labels import LABELS_SCHEMA_VERSION, SEPSIS3_SQL_FILES
from eval.mimic_study.labels.materialize import build_label_artifact, write_label_artifact
from eval.mimic_study.labels.pins import (
    LabelPinError,
    load_pin,
    pin_from_repo,
    validate_pin,
    write_pin,
)


def _make_mimic_code_repo(tmp: Path) -> Path:
    repo = tmp / "mimic-code"
    sql_files = {
        **SEPSIS3_SQL_FILES,
    }
    for index, rel in enumerate(sql_files.values(), start=1):
        sql_path = repo / rel
        sql_path.parent.mkdir(parents=True, exist_ok=True)
        sql_path.write_text(f"-- {rel}\nSELECT {index};\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def test_pin_from_repo_records_commit_and_hashes(tmp_path: Path) -> None:
    repo = _make_mimic_code_repo(tmp_path)
    pin = pin_from_repo(repo, sql_files=SEPSIS3_SQL_FILES)
    assert pin["schema_version"] == LABELS_SCHEMA_VERSION
    assert pin["mimic_code"]["revision"] == "HEAD"
    assert pin["mimic_code"]["resolved_commit"] == subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo
    ).stdout.strip()
    files = pin["mimic_code"]["files"]
    assert set(files) == set(SEPSIS3_SQL_FILES.values())
    assert all(len(info["sha256"]) == 64 for info in files.values())
    validate_pin(pin)


def test_write_and_load_pin(tmp_path: Path) -> None:
    repo = _make_mimic_code_repo(tmp_path)
    pin = pin_from_repo(repo, sql_files=SEPSIS3_SQL_FILES)
    out = write_pin(pin, tmp_path / "pin.json")
    loaded = load_pin(out)
    assert loaded["mimic_code"]["resolved_commit"] == pin["mimic_code"]["resolved_commit"]


def test_load_pin_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(LabelPinError, match="no mimic-code label pin"):
        load_pin(tmp_path / "does-not-exist.json")


def test_validate_pin_detects_tampering(tmp_path: Path) -> None:
    repo = _make_mimic_code_repo(tmp_path)
    pin = pin_from_repo(repo, sql_files=SEPSIS3_SQL_FILES)
    first = list(pin["mimic_code"]["files"])[0]
    pin["mimic_code"]["files"][first].pop("sha256")
    with pytest.raises(LabelPinError, match="missing sha256"):
        validate_pin(pin)


def test_pin_missing_sql_file_fails(tmp_path: Path) -> None:
    repo = _make_mimic_code_repo(tmp_path)
    with pytest.raises(LabelPinError, match="missing SQL file"):
        pin_from_repo(repo, sql_files={"x": "mimic-iv/concepts/sepsis/nope.sql"})


def test_replay_never_imports_labels() -> None:
    # The feature-replay path must not load the labels package (module boundary).
    import sys

    for name in [n for n in sys.modules if n.startswith("eval.mimic_study.labels")]:
        del sys.modules[name]
    from eval.mimic_study import index_replay  # noqa: F401

    assert not [n for n in sys.modules if n.startswith("eval.mimic_study.labels")]


def test_materialize_labels_is_sorted_hashed_and_preserves_unknowns(tmp_path: Path) -> None:
    repo = _make_mimic_code_repo(tmp_path)
    pin = pin_from_repo(repo, sql_files=SEPSIS3_SQL_FILES)
    artifact = build_label_artifact(
        cohort_stay_ids=["s3", "s1", "s2"],
        sepsis_rows=[
            {"stay_id": "s1", "sepsis3": "1", "sofa_time": "2019-01-01 04:00:00"},
            {"stay_id": "s1", "sepsis3": "1", "sofa_time": "2019-01-01 03:00:00"},
            {"stay_id": "s2", "sepsis3": "0", "sofa_time": "2019-01-01 02:00:00"},
        ],
        kdigo_rows=[
            {"stay_id": "s1", "kdigo_stage": "2", "event_time": "2019-01-01 05:00:00"},
            {"stay_id": "s1", "kdigo_stage": "1", "event_time": "2019-01-01 02:00:00"},
        ],
        protocol_id="mimic-iv-governance-study.v2",
        dataset_pin={"name": "mimic-iv", "version": "3.1", "extract_date": "2026-09-06"},
        source_pin=pin,
    )

    assert [row["stay_id"] for row in artifact["stays"]] == ["s1", "s2", "s3"]
    assert artifact["stays"][0]["sepsis3_onset"] == "2019-01-01T03:00:00"
    assert artifact["stays"][0]["aki_kdigo_max_stage"] == 2
    assert artifact["stays"][1]["sepsis3_onset"] is None
    assert artifact["stays"][2]["sepsis3_onset"] is None
    assert artifact["stays"][2]["aki_kdigo_stage_ge_1"] is None
    assert len(artifact["content_hash"]) == 64

    out = write_label_artifact(artifact, tmp_path / "labels.json")
    assert out.is_file()
