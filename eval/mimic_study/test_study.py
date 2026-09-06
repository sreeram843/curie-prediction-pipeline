"""CURIE-016: locked MIMIC ablation / robustness study."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.mimic_harness.replay import FIXTURES_DIR
from eval.mimic_study.ablations import ABLATION_KNOBS
from eval.mimic_study.protocol import ProtocolError, assert_split_allowed_for_tuning
from eval.mimic_study.study import (
    main,
    run_study,
    run_study_rows,
    select_operating_point,
)
from eval.mimic_study.study_replay import replay_stay_ablation


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
    assert gov["score_trajectory"]


def test_naive_count_includes_aki_like_governed_count_does() -> None:
    """naive_alert_count and governed_alert_count must cover the same indicator
    population. Regression for a bug where governed_alert_count summed SOFA +
    AKI (via _emit_signal) but naive_alert_count only ever counted SOFA,
    inflating the apparent alert-reduction ratio on any stay with AKI signals."""
    stay = {
        "stay_id": "mixed-1",
        "subject_id": "s-mixed-1",
        "hadm_id": "h-mixed-1",
        "intime": "2019-01-01 00:00:00",
        "outtime": "2019-01-03 00:00:00",
        "labels": {"sepsis3_onset": None, "aki_kdigo_stage_ge_1": None},
        "labs": [
            # Baseline creatinine, then a 2x rise within the KDIGO window -> AKI stage.
            {
                "itemid": 50912,
                "valuenum": 1.0,
                "unit": "mg/dL",
                "charttime": "2019-01-01 06:00:00",
                "storetime": "2019-01-01 06:00:00",
                "evidence_id": "lab/cr-baseline",
            },
            {
                "itemid": 50912,
                "valuenum": 2.0,
                "unit": "mg/dL",
                "charttime": "2019-01-01 18:00:00",
                "storetime": "2019-01-01 18:00:00",
                "evidence_id": "lab/cr-doubled",
            },
        ],
        "charts": [
            # Low MAP -> SOFA cardiovascular deterioration, independent of AKI.
            {
                "itemid": 220052,
                "valuenum": 50,
                "unit": "mmHg",
                "charttime": "2019-01-01 07:00:00",
                "storetime": "2019-01-01 07:00:00",
                "evidence_id": "chart/map-low",
            }
        ],
        "conditions": [],
    }
    result = replay_stay_ablation(stay, knobs=None)
    # Sanity: both indicators actually fired, or this test proves nothing.
    assert result["naive_sofa_alert_count"] > 0
    assert result["naive_aki_alert_count"] > 0
    # knobs=None is a pure passthrough in _emit_signal (no governance filtering),
    # so with identical indicator coverage on both sides these must be exactly equal.
    assert result["naive_alert_count"] == result["governed_alert_count"]
    assert result["naive_alert_count"] == (
        result["naive_sofa_alert_count"] + result["naive_aki_alert_count"]
    )
    assert result["score_trajectory"]


def test_frozen_artifacts_regenerated_by_run(tmp_path: Path) -> None:
    result = run_study(write_frozen=True, frozen_dir=tmp_path)
    op_path = tmp_path / "operating_point.v1.json"
    man_path = tmp_path / "study_manifest.v1.json"
    assert op_path.is_file()
    assert man_path.is_file()
    manifest = json.loads(man_path.read_text())
    assert manifest["content_hash"] == result["manifest"]["content_hash"]
    assert manifest["module"] == "python -m eval.mimic_study.study run"


def test_v2_study_rows_uses_explicit_protocol_and_versioned_outputs(tmp_path: Path) -> None:
    from eval.mimic_study.protocol import load_protocol

    fixture = json.loads((FIXTURES_DIR / "demo_schema_stays.v1.json").read_text())
    result = run_study_rows(
        fixture["stays"],
        fixture_meta=fixture,
        protocol=load_protocol(version="v2"),
        write_frozen=True,
        frozen_dir=tmp_path,
    )

    assert result["report"]["protocol_id"] == "mimic-iv-governance-study.v2"
    assert result["manifest"]["protocol_id"] == "mimic-iv-governance-study.v2"
    assert result["manifest"]["operating_point_path"].endswith("operating_point.v2.json")
    assert (tmp_path / "operating_point.v2.json").is_file()
    assert (tmp_path / "study_manifest.v2.json").is_file()
