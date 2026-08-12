"""CURIE-001: resolved Challenge study bundle integrity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.challenge2019.study_bundle import (
    STUDY_BUNDLE_V1,
    STUDY_BUNDLE_V1_SHA,
    StudyBundleError,
    expected_content_hash,
    load_resolved_study_bundle,
)
from eval.indicators.registry import content_hash, load_rule_bundle


def test_study_bundle_min_components_is_two() -> None:
    bundle = load_resolved_study_bundle()
    assert bundle["score"]["min_components_required"] == 2
    assert bundle["study_artifact"] is True
    assert bundle["bundle_id"] == "sepsis-sofa-challenge2019-p1"
    assert bundle["content_hash"] == expected_content_hash()


def test_study_bundle_hash_matches_sidecar() -> None:
    raw = json.loads(STUDY_BUNDLE_V1.read_text())
    digest = content_hash(raw)
    assert digest == STUDY_BUNDLE_V1_SHA.read_text().strip()


def test_study_bundle_hash_drift_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from eval.challenge2019 import study_bundle as sb

    mutated = json.loads(STUDY_BUNDLE_V1.read_text())
    mutated["description"] = "tampered"
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(mutated, indent=2, sort_keys=True) + "\n")
    monkeypatch.setattr(sb, "STUDY_BUNDLE_V1_SHA", STUDY_BUNDLE_V1_SHA)
    with pytest.raises(StudyBundleError, match="hash drift"):
        load_resolved_study_bundle(path, verify_hash=True)


def test_product_v030_is_not_the_study_artifact() -> None:
    product = load_rule_bundle("sepsis-sofa", "0.3.0")
    study = load_resolved_study_bundle()
    assert product["score"]["min_components_required"] == 3
    assert study["score"]["min_components_required"] == 2
    assert product.get("study_artifact") is not True
    assert product["content_hash"] != study["content_hash"]
