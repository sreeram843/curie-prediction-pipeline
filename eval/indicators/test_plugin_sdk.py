"""CURIE-011: indicator plugin SDK."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.indicators.plugin import (
    IndicatorPlugin,
    PluginError,
    dispatch_score,
    get_plugin,
    list_plugins,
    register_plugin,
    require_plugin,
)
from eval.indicators.registry import (
    RuleBundleError,
    list_indicators,
    load_rule_bundle,
    validate_activation,
)


def test_sofa_aki_and_resp_registered_and_dispatchable() -> None:
    plugins = {p.score_type: p for p in list_plugins()}
    assert "sofa" in plugins
    assert "aki_kdigo" in plugins
    assert "resp_hypoxemia" in plugins
    sofa = dispatch_score("sofa")
    aki = dispatch_score("aki_kdigo")
    resp = dispatch_score("resp_hypoxemia")
    assert callable(sofa)
    assert callable(aki)
    assert callable(resp)
    assert plugins["sofa"].runtime_impl["java"]
    assert plugins["aki_kdigo"].runtime_impl["java"]
    assert plugins["resp_hypoxemia"].indicator == "respiratory-deterioration"


def test_list_indicators_proves_scorer_installed() -> None:
    rows = list_indicators(installed_only=True)
    assert rows
    assert all(r["scorer_installed"] is True for r in rows)
    assert all("plugin_id" in r and "runtime_impl" in r for r in rows)
    indicators = {r["indicator"] for r in rows}
    assert "sofa-deterioration" in indicators
    assert "aki" in indicators
    assert "respiratory-deterioration" in indicators


def test_load_bundle_requires_installed_scorer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.indicators import registry as reg

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    doc = {
        "bundle_id": "orphan-score",
        "version": "0.1.0",
        "indicator": "orphan",
        "score": {"type": "not_a_real_scorer"},
    }
    (bundles / "orphan-score.v0.1.0.json").write_text(json.dumps(doc))
    monkeypatch.setattr(reg, "BUNDLES_DIR", bundles)
    with pytest.raises(RuleBundleError, match="No scorer plugin"):
        load_rule_bundle("orphan-score", "0.1.0", require_scorer=True)
    # Explicit bypass for harness fixtures
    loaded = load_rule_bundle("orphan-score", "0.1.0", require_scorer=False)
    assert loaded["score"]["type"] == "not_a_real_scorer"


def test_resp_plugin_never_resolves_to_sofa_scorer() -> None:
    plugins = {p.score_type: p for p in list_plugins()}
    resp = plugins["resp_hypoxemia"]
    sofa = plugins["sofa"]
    assert resp.scorer_attr == "compute_resp_score"
    assert "RespScorer" in (resp.runtime_impl.get("java") or "")
    assert resp.resolve_scorer() is not sofa.resolve_scorer()
    assert resp.scorer_module != sofa.scorer_module


def test_validate_activation_rejects_unsupported_score_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.indicators import registry as reg

    bundles = tmp_path / "bundles"
    bundles.mkdir()
    doc = {
        "bundle_id": "future-hepatic",
        "version": "0.1.0",
        "indicator": "hepatic-deterioration",
        "score": {"type": "hepatic_not_installed"},
    }
    (bundles / "future-hepatic.v0.1.0.json").write_text(json.dumps(doc))
    activation = tmp_path / "activation.json"
    activation.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "active": {"future-hepatic": "0.1.0"},
            }
        )
    )
    monkeypatch.setattr(reg, "BUNDLES_DIR", bundles)
    monkeypatch.setattr(reg, "ACTIVATION_PATH", activation)
    with pytest.raises(RuleBundleError, match="Activation failed"):
        validate_activation(activation)


def test_validate_activation_passes_for_repo_manifest() -> None:
    report = validate_activation()
    assert report["ok"] is True
    assert "sepsis-sofa" in report["active"]
    assert "aki-kdigo" in report["active"]
    assert "resp-deterioration" in report["active"]
    assert report["active"]["sepsis-sofa"]["scorer_installed"] is True
    assert report["active"]["aki-kdigo"]["scorer_installed"] is True
    assert report["active"]["resp-deterioration"]["scorer_installed"] is True
    assert "hemo-shock" in report["active"]
    assert report["active"]["hemo-shock"]["scorer_installed"] is True


def test_require_plugin_unknown() -> None:
    with pytest.raises(PluginError, match="No scorer plugin"):
        require_plugin("definitely-missing-type")


def test_register_custom_plugin_then_dispatch() -> None:
    plugin = IndicatorPlugin(
        plugin_id="test-demo-plugin",
        score_type="test_demo_score",
        indicator="demo",
        signal_kind="risk",
        display_name="Demo",
        bundle_id="demo",
        clinical_concepts=("x",),
        codes=(),
        units=(),
        windows={},
        eligibility="test",
        exclusions=(),
        missing_data_policy="none",
        resolution_rule="none",
        scorer_module="eval.aki.scoring",
        scorer_attr="compute_aki_score",
        tier_module="eval.aki.scoring",
        tier_attr="tier_for_aki_score",
        runtime_impl={"python": "eval.aki.scoring.compute_aki_score"},
    )
    register_plugin(plugin)
    assert get_plugin("test_demo_score") is plugin
    assert dispatch_score("test_demo_score") is plugin.resolve_scorer()
