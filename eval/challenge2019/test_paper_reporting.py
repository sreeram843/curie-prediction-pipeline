"""Publication-reporting contracts for the frozen Challenge 2019 study."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.challenge2019.paper_analyses import build_holdout_sidecar, write_frozen

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "eval" / "challenge2019" / "frozen"


def test_v3_holdout_sidecar_carries_coprimary_and_burden_context() -> None:
    report = {
        "stays_scored": 3,
        "cohort": {
            "sepsis_stays": 1,
            "non_sepsis_stays": 2,
            "patient_hours": 72,
            "patient_days": 3.0,
        },
        "alerts": {
            "naive_total": 9,
            "governed_total": 6,
            "interruptive_total": 3,
            "governed_alerts_per_patient_day": 2.0,
            "interruptive_alerts_per_patient_day": 1.0,
            "interruptive_reduction_ratio": 1 / 3,
        },
        "detection": {
            "naive_tp": 1,
            "governed_tp": 1,
            "interruptive_tp": 1,
            "governed_sensitivity": 1.0,
            "interruptive_sensitivity": 1.0,
            "governed_ppv_stay": 0.5,
            "interruptive_ppv_stay": 0.5,
            "governed_fp_non_sepsis": 1,
            "interruptive_fp_non_sepsis": 1,
            "interruptive_nna": 3.0,
            "mean_lead_hours_governed_in_window": 2.0,
            "lead_hours_governed_in_window_p25": 1.0,
            "lead_hours_governed_in_window_p50": 2.0,
            "lead_hours_governed_in_window_p75": 3.0,
        },
        "challenge_utility": {
            "naive": {"normalized_utility": 0.4},
            "governed": {"normalized_utility": 0.3},
            "interruptive": {"normalized_utility": 0.2},
        },
        "bootstrap": {"n_boot": 0, "seed": 42, "metrics": {}},
        "rule_bundle": {"content_hash": "abc"},
    }

    sidecar = build_holdout_sidecar(report)

    assert sidecar["schema_version"] == "3.0.0"
    assert sidecar["challenge_utility"]["governed"]["normalized_utility"] == 0.3
    assert sidecar["cohort"]["patient_days"] == 3.0
    assert sidecar["alerts"]["interruptive_alerts_per_patient_day"] == 1.0
    assert sidecar["detection"]["interruptive_ppv_stay"] == 0.5
    assert sidecar["detection"]["lead_hours_governed_in_window_p50"] == 2.0


def test_frozen_selection_grid_preserves_all_original_candidates() -> None:
    payload = json.loads(
        (FROZEN / "selection_grid_setA_grace6.v1.json").read_text(encoding="utf-8")
    )
    assert payload["selection_detection_mode"] == "legacy_grace_6"
    assert payload["winner_id"] == "grid_p0_r90_b0"
    assert len(payload["candidates"]) == 23
    assert payload["source_sha256"] == (
        "8eadb212618bea820a39e0c260a4b503ecde292b843538def5203a4fb9b9c721"
    )


def test_frozen_writer_refuses_to_replace_existing_version(tmp_path: Path) -> None:
    existing = tmp_path / "holdout_primary_window_m12_p6.v3.json"
    existing.write_text('{"old": true}\n', encoding="utf-8")
    report = {
        "holdout_sidecar": {"new": True},
        "comparators": None,
        "ablation": None,
        "miss_analysis": None,
        "pareto": None,
    }
    with pytest.raises(FileExistsError, match="new artifact version"):
        write_frozen(report, frozen_dir=tmp_path)
    assert existing.read_text(encoding="utf-8") == '{"old": true}\n'
