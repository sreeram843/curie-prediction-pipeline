"""CURIE-016: locked MIMIC ablation / robustness study."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.mimic_study.ablations import ABLATION_KNOBS
from eval.mimic_study.protocol import ProtocolError, assert_split_allowed_for_tuning
from eval.mimic_study.study import (
    MANIFEST_PATH,
    OPERATING_POINT_PATH,
    main,
    run_study,
    select_operating_point,
)
from eval.mimic_study.study_replay import replay_stay_ablation
from eval.mimic_harness.replay import FIXTURES_DIR


def test_all_protocol_ablations_defined() -> None:
    from eval.mimic_study.protocol import load_protocol

    expected = set(load_protocol()["ablations"]["pre_specified"])
    assert set(ABLATION_KNOBS) == expected


def test_selection_forbidden_on_test() -> None:
    with pytest.raises(ProtocolError, match="forbidden"):
        assert_split_allowed_for_tuning("test", command="operating_point_selection")


def test_run_study_selects_without_test_and_writes_manifest(tmp_path: Path) -> None:
    # Run without writing to repo frozen/ — use no_write then write locally
    result = run_study(write_frozen=False)
    report = result["report"]
    assert report["selection_guard"]["test_used_for_selection"] is False
    assert "development" in report["selection_guard"]["tuned_on"]
    assert report["operating_point"]["candidate_id"]
    assert "meets_pe1" in report["primary_test"]
    assert set(report["ablations_test"]) == set(ABLATION_KNOBS)
    assert result["manifest"]["primary_eval_once"] is True
    assert result["manifest"]["regenerate_command"] == "make mimic-study"

    # Thresholds not selected on test: re-select and ensure candidate comes from cal
    stays = json.loads((FIXTURES_DIR / "demo_schema_stays.v1.json").read_text())["stays"]
    op = select_operating_point(stays)
    assert op["forbidden_selection_split"] == "test"
    assert "test" not in op["source_splits"]


def test_cli_run_and_guard() -> None:
    assert main(["guard-test"]) == 0
    assert main(["run", "--no-write"]) == 0


def test_naive_vs_governed_replay_differs_on_positive_stay() -> None:
    stays = json.loads((FIXTURES_DIR / "demo_schema_stays.v1.json").read_text())["stays"]
    stay = next(s for s in stays if s["stay_id"] == "stay-demo-002")
    naive = replay_stay_ablation(stay, knobs=None)
    from eval.mimic_study.ablations import FULL_GOVERNANCE_KNOBS

    gov = replay_stay_ablation(stay, knobs=FULL_GOVERNANCE_KNOBS)
    assert naive["naive_alert_count"] >= 1
    # Governed should not exceed naive alert count
    assert gov["governed_alert_count"] <= naive["naive_alert_count"]


def test_frozen_artifacts_regenerated_by_run() -> None:
    result = run_study(write_frozen=True)
    assert OPERATING_POINT_PATH.is_file()
    assert MANIFEST_PATH.is_file()
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["content_hash"] == result["manifest"]["content_hash"]
    assert manifest["module"] == "python -m eval.mimic_study.study run"
