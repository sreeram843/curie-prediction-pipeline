"""CURIE-014: frozen MIMIC-IV study protocol guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.mimic_study.protocol import (
    PROTOCOL_PATH,
    ProtocolError,
    assert_command_allowed_on_split,
    assert_split_allowed_for_tuning,
    claims_evidence_map,
    load_protocol,
    normalize_split_id,
    operating_point_selection_rule,
    primary_endpoint,
    protocol_summary,
)
from eval.mimic_study.sweep import main, run_operating_point_selection, run_sweep


def test_protocol_file_frozen_and_complete() -> None:
    assert PROTOCOL_PATH.is_file()
    proto = load_protocol()
    assert proto["status"] == "frozen"
    assert proto["protocol_id"] == "mimic-iv-governance-study.v1"
    pe = primary_endpoint(proto)
    assert pe["id"] == "PE-1"
    assert "governed_sensitivity" in pe["success_rule"]
    assert pe["evaluated_on"] == "test"
    assert pe["one_shot"] is True
    ops = operating_point_selection_rule(proto)
    assert ops["forbidden_on_test"] is True
    assert "calibration" in ops["rule"].lower() or "development" in ops["rule"].lower()
    claims = claims_evidence_map(proto)
    assert any(c["claim_id"] == "C1" for c in claims)
    assert any(c["status"] == "non_claim" for c in claims)
    splits = proto["splits"]
    assert set(splits) >= {"development", "calibration", "test"}
    assert "sweep" in splits["test"]["forbidden_commands"]


def test_test_split_aliases_normalize() -> None:
    assert normalize_split_id("holdout") == "test"
    assert normalize_split_id("temporal_holdout") == "test"
    assert normalize_split_id("TRAIN") == "development"
    assert normalize_split_id("val") == "calibration"


@pytest.mark.parametrize(
    "split,command",
    [
        ("test", "sweep"),
        ("holdout", "tune"),
        ("temporal_holdout", "grid_search"),
        ("test", "threshold_search"),
        ("test", "operating_point_selection"),
    ],
)
def test_tuning_forbidden_on_test(split: str, command: str) -> None:
    with pytest.raises(ProtocolError, match="forbidden"):
        assert_command_allowed_on_split(split, command)


def test_sweep_allowed_on_development() -> None:
    assert_split_allowed_for_tuning("development", command="sweep")
    report = run_sweep(split="development")
    assert report["status"] == "dry_run"
    assert report["split"] == "development"


def test_sweep_api_rejects_test_split() -> None:
    with pytest.raises(ProtocolError, match="forbidden"):
        run_sweep(split="test")
    with pytest.raises(ProtocolError, match="forbidden"):
        run_operating_point_selection(split="test")


def test_cli_sweep_on_test_exits_nonzero() -> None:
    assert main(["sweep", "--split", "test"]) == 2
    assert main(["sweep", "--split", "development"]) == 0
    assert main(["show", "--json"]) == 0


def test_protocol_summary_stable_keys() -> None:
    summary = protocol_summary()
    raw = json.loads(PROTOCOL_PATH.read_text())
    assert summary["protocol_id"] == raw["protocol_id"]
    assert "primary_success_rule" in summary
    assert "sweep" in summary["test_forbidden_commands"]


def test_docs_protocol_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    doc = root / "docs" / "mimic-iv-study-protocol.md"
    assert doc.is_file()
    text = doc.read_text()
    assert "PE-1" in text
    assert "operating-point" in text.lower() or "operating point" in text.lower()
    assert "product claims" in text.lower() or "claims" in text.lower()
