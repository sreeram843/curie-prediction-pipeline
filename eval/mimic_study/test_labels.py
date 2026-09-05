"""Tests for the pinned mimic-code label references (Phase C3 pinning, kept
separate from feature replay)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from eval.mimic_study.labels import LABELS_SCHEMA_VERSION, SEPSIS3_SQL_FILES
from eval.mimic_study.labels.pins import (
    LabelPinError,
    load_pin,
    pin_from_repo,
    validate_pin,
    write_pin,
)


def _make_mimic_code_repo(tmp: Path) -> Path:
    repo = tmp / "mimic-code"
    sql_dir = repo / "mimic-iv" / "concepts" / "sepsis"
    sql_dir.mkdir(parents=True)
    (sql_dir / "suspicion_of_infection.sql").write_text("-- soi\nSELECT 1;\n")
    (sql_dir / "sepsis3.sql").write_text("-- sepsis3\nSELECT 2;\n")
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
