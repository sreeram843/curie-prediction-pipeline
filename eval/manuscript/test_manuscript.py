"""Tests for CURIE-020 manuscript package."""

from __future__ import annotations

import json
from pathlib import Path

from eval.manuscript.package import (
    MANIFEST_FILENAME,
    build,
    challenge_results,
    claim_tiers,
    robustness_table,
    scan_for_phi,
)


def test_build_writes_manifest_without_phi(tmp_path: Path) -> None:
    result = build(write=True, frozen_out=tmp_path, generated_out=tmp_path)
    manifest = result["manifest"]
    assert manifest["manifest_version"] == "2.0.0"
    assert manifest["curie_ticket"] == "CURIE-020"
    assert manifest["result_scope"]["dataset"] == "physionet-challenge-2019"
    assert manifest["result_scope"]["other_datasets_are_results"] is False
    assert manifest["phi_policy"]["commits_patient_level_data"] is False
    assert all(v.get("present") for v in manifest["artifact_pins"].values())
    assert scan_for_phi(json.dumps(manifest)) == []
    assert (tmp_path / MANIFEST_FILENAME).is_file()
    assert (tmp_path / "tables.md").is_file()
    assert (tmp_path / "figure_specs.v2.json").is_file()
    assert "MIMIC demo sensitivity" not in result["tables_md"]


def test_claim_tiers_separate_outcomes() -> None:
    tiers = claim_tiers()
    assert tiers["clinical_outcome_effects"]["status"] == "not_claimed"
    assert tiers["retrospective_detection"]["dataset"] == "physionet-challenge-2019"
    assert tiers["alert_policy_utility"]["dataset"] == "physionet-challenge-2019"
    assert all(
        "demo" not in item.lower()
        for tier in tiers.values()
        for item in tier.get("includes", [])
    )


def test_challenge_results_are_locked_to_allowed_numbers() -> None:
    results = challenge_results()
    assert results["setA"]["n_stays"] == 20336
    assert results["setA"]["interruptive_reduction_ratio"] == 0.12251536914246035
    assert results["setB"]["n_stays"] == 20000
    assert results["setB"]["governed_sensitivity"] == 0.795
    assert results["setB"]["interruptive_sensitivity"] == 0.34
    assert results["setB"]["interruptive_nna"] == 106.1
    assert results["setB"]["mean_lead_hours_in_window"] == 5.97


def test_robustness_is_sensitivity_analysis_only() -> None:
    rows = robustness_table()
    assert rows
    assert all(row["role"] == "sensitivity_analysis" for row in rows)
    assert any(row["detection_mode_id"] == "grace_6" for row in rows)


def test_phi_scan_flags_hadm() -> None:
    assert scan_for_phi("cohort hadm_id=12345") != []
    assert scan_for_phi("policy forbids hadm_id lists") == []
    assert scan_for_phi("aggregate sensitivity 0.81") == []
