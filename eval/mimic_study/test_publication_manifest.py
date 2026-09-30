"""Tests for the immutable v2 to publication-safe v3 manifest repair."""

from __future__ import annotations

import json

import pytest

from eval.mimic_harness.replay import stable_report_hash
from eval.mimic_study.publication_manifest import (
    EXPECTED_SOURCE_HASH,
    NUMERICAL_SECTIONS,
    SOURCE_PATH,
    write_publication_manifest,
)


def test_publication_manifest_repairs_only_provenance(tmp_path) -> None:
    source = json.loads(SOURCE_PATH.read_text())
    output_path = tmp_path / "study_manifest.v3.json"
    repaired = write_publication_manifest(output_path=output_path)

    assert source["content_hash"] == EXPECTED_SOURCE_HASH
    assert repaired["manifest_version"] == "2.0.0"
    assert repaired["input_source"]["kind"] == "indexed_stream"
    assert "fixture" not in repaired
    assert repaired["source_manifest"]["content_hash"] == EXPECTED_SOURCE_HASH
    for section in NUMERICAL_SECTIONS:
        assert repaired[section] == source[section]
    assert repaired["content_hash"] == stable_report_hash(
        {key: value for key, value in repaired.items() if key != "content_hash"}
    )
    assert json.loads(output_path.read_text()) == repaired


def test_publication_manifest_rejects_unreviewed_source_hash(tmp_path) -> None:
    source = json.loads(SOURCE_PATH.read_text())
    source["test_primary"]["stays"] += 1
    source["content_hash"] = stable_report_hash(
        {key: value for key, value in source.items() if key != "content_hash"}
    )
    path = tmp_path / "altered-v2.json"
    path.write_text(json.dumps(source))
    assert source["content_hash"] != EXPECTED_SOURCE_HASH
    with pytest.raises(ValueError, match="does not match the reviewed source"):
        write_publication_manifest(source_path=path, output_path=tmp_path / "v3.json")
