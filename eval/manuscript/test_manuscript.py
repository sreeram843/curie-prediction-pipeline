"""Tests for CURIE-020 manuscript package."""

from __future__ import annotations

import json

from eval.manuscript.package import (
    FROZEN_OUT,
    GENERATED_OUT,
    ablation_table,
    build,
    claim_tiers,
    scan_for_phi,
)


def test_build_writes_manifest_without_phi() -> None:
    result = build(write=True)
    manifest = result["manifest"]
    assert manifest["manifest_version"] == "1.0.0"
    assert manifest["curie_ticket"] == "CURIE-020"
    assert manifest["phi_policy"]["commits_patient_level_mimic"] is False
    assert all(v.get("present") for v in manifest["artifact_pins"].values())
    assert scan_for_phi(json.dumps(manifest)) == []
    assert (FROZEN_OUT / "reproducibility_manifest.v1.json").is_file()
    assert (GENERATED_OUT / "tables.md").is_file()
    assert (GENERATED_OUT / "figure_specs.v1.json").is_file()


def test_claim_tiers_separate_outcomes() -> None:
    tiers = claim_tiers()
    assert tiers["clinical_outcome_effects"]["status"] == "not_claimed"
    assert tiers["retrospective_detection"]["status"].startswith("demonstrated")
    assert tiers["alert_policy_utility"]["status"].startswith("demonstrated")


def test_ablation_table_nonempty() -> None:
    rows = ablation_table()
    assert any(r["ablation_id"] == "primary_operating_point" for r in rows)
    assert any(r["ablation_id"] == "threshold_only_naive" for r in rows)


def test_phi_scan_flags_hadm() -> None:
    assert scan_for_phi("cohort hadm_id=12345") != []
    assert scan_for_phi("policy forbids hadm_id lists") == []
    assert scan_for_phi("aggregate sensitivity 0.81") == []
