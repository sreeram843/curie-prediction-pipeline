"""CURIE-002: semantic version resolution for rule bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.indicators.registry import (
    RuleBundleError,
    load_rule_bundle,
    max_version,
    resolve_bundle_version,
)
from eval.indicators.semver import compare_semver, parse_semver


def test_semver_orders_0_9_before_0_10() -> None:
    assert parse_semver("0.9.0") < parse_semver("0.10.0")
    assert compare_semver("0.9.0", "0.10.0") < 0
    assert max_version(["0.9.0", "0.10.0", "0.2.0"]) == "0.10.0"


def test_invalid_semver_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid semver"):
        parse_semver("v1")
    with pytest.raises(ValueError, match="Invalid semver"):
        parse_semver("1.2")
    with pytest.raises(RuleBundleError):
        resolve_bundle_version("sepsis-sofa", "not-a-version")


def test_latest_uses_activation_manifest_not_lexical() -> None:
    # Lexical max of v0.1 / v0.2 / v0.3 is still 0.3.0, but activation is authoritative
    ver = resolve_bundle_version("sepsis-sofa", "latest")
    assert ver == "0.3.0"
    bundle = load_rule_bundle("sepsis-sofa")
    assert bundle["version"] == "0.3.0"
    assert len(bundle["content_hash"]) == 64


def test_explicit_version_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = load_rule_bundle("sepsis-sofa", "0.2.0")
    assert bundle["version"] == "0.2.0"


def test_require_explicit_version_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURIE_REQUIRE_EXPLICIT_RULE_VERSION", "1")
    with pytest.raises(RuleBundleError, match="Explicit rule version"):
        load_rule_bundle("sepsis-sofa")
    bundle = load_rule_bundle("sepsis-sofa", "0.3.0")
    assert bundle["version"] == "0.3.0"


def test_invalid_bundle_missing_score_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.indicators import registry as reg

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    bad = {
        "bundle_id": "demo-bad",
        "version": "0.1.0",
        "indicator": "demo",
        "score": {},
    }
    (bundles / "demo-bad.v0.1.0.json").write_text(json.dumps(bad))
    monkeypatch.setattr(reg, "BUNDLES_DIR", bundles)
    with pytest.raises(RuleBundleError, match="score.type"):
        load_rule_bundle("demo-bad", "0.1.0")


def test_activation_latest_picks_semver_not_lexically_larger_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove 0.10.0 wins over 0.9.0 via activation, not string sort of paths."""
    from eval.indicators import registry as reg

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    for ver in ("0.9.0", "0.10.0"):
        doc = {
            "bundle_id": "demo-order",
            "version": ver,
            "indicator": "demo",
            "score": {"type": "demo"},
        }
        (bundles / f"demo-order.v{ver}.json").write_text(json.dumps(doc))
    activation = tmp_path / "activation.json"
    activation.write_text(
        json.dumps({"schema_version": "1.0.0", "active": {"demo-order": "0.10.0"}})
    )
    monkeypatch.setattr(reg, "BUNDLES_DIR", bundles)
    monkeypatch.setattr(reg, "ACTIVATION_PATH", activation)
    # Filename sort would put v0.9.0 after v0.10.0 lexicographically — activation wins
    assert sorted(bundles.glob("demo-order.v*.json"))[-1].name == "demo-order.v0.9.0.json"
    bundle = load_rule_bundle("demo-order")
    assert bundle["version"] == "0.10.0"
