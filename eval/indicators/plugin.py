"""Indicator plugin SDK (CURIE-011).

A JSON rule bundle alone cannot claim a scorer that is not installed. Plugins
declare clinical concepts, runtime mappings, and the Python callable used for
reference scoring / activation checks.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class PluginError(ValueError):
    """Invalid plugin registration or missing scorer for a score.type."""


@dataclass(frozen=True)
class IndicatorPlugin:
    """Bounded contract for adding an indicator without a platform rewrite."""

    plugin_id: str
    score_type: str
    indicator: str
    signal_kind: str  # risk | phenotype
    display_name: str
    bundle_id: str
    clinical_concepts: tuple[str, ...]
    codes: tuple[str, ...]
    units: tuple[str, ...]
    windows: dict[str, str]
    eligibility: str
    exclusions: tuple[str, ...]
    missing_data_policy: str
    resolution_rule: str
    # Import path to a callable used as the reference scorer proof
    scorer_module: str
    scorer_attr: str
    tier_module: str
    tier_attr: str
    runtime_impl: dict[str, str]
    fixture_paths: tuple[str, ...] = ()
    notes: str = ""

    def resolve_scorer(self) -> Callable[..., Any]:
        mod = importlib.import_module(self.scorer_module)
        fn = getattr(mod, self.scorer_attr, None)
        if fn is None or not callable(fn):
            raise PluginError(
                f"Plugin {self.plugin_id!r}: scorer "
                f"{self.scorer_module}.{self.scorer_attr} is not callable"
            )
        return fn

    def resolve_tier_fn(self) -> Callable[..., Any]:
        mod = importlib.import_module(self.tier_module)
        fn = getattr(mod, self.tier_attr, None)
        if fn is None or not callable(fn):
            raise PluginError(
                f"Plugin {self.plugin_id!r}: tier fn "
                f"{self.tier_module}.{self.tier_attr} is not callable"
            )
        return fn

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "score_type": self.score_type,
            "indicator": self.indicator,
            "signal_kind": self.signal_kind,
            "display_name": self.display_name,
            "bundle_id": self.bundle_id,
            "clinical_concepts": list(self.clinical_concepts),
            "codes": list(self.codes),
            "units": list(self.units),
            "windows": dict(self.windows),
            "eligibility": self.eligibility,
            "exclusions": list(self.exclusions),
            "missing_data_policy": self.missing_data_policy,
            "resolution_rule": self.resolution_rule,
            "scorer": f"{self.scorer_module}.{self.scorer_attr}",
            "tier_fn": f"{self.tier_module}.{self.tier_attr}",
            "runtime_impl": dict(self.runtime_impl),
            "fixture_paths": list(self.fixture_paths),
            "scorer_installed": True,
            "notes": self.notes,
        }


_PLUGINS_BY_SCORE_TYPE: dict[str, IndicatorPlugin] = {}
_PLUGINS_BY_ID: dict[str, IndicatorPlugin] = {}


def register_plugin(plugin: IndicatorPlugin, *, verify: bool = True) -> IndicatorPlugin:
    """Register a plugin. Verifies scorer/tier callables import by default."""
    if not plugin.score_type or not plugin.plugin_id:
        raise PluginError("plugin_id and score_type are required")
    if plugin.score_type in _PLUGINS_BY_SCORE_TYPE:
        existing = _PLUGINS_BY_SCORE_TYPE[plugin.score_type]
        if existing.plugin_id != plugin.plugin_id:
            raise PluginError(
                f"score.type {plugin.score_type!r} already registered by "
                f"{existing.plugin_id!r}"
            )
        return existing
    if plugin.plugin_id in _PLUGINS_BY_ID:
        raise PluginError(f"plugin_id {plugin.plugin_id!r} already registered")
    if verify:
        plugin.resolve_scorer()
        plugin.resolve_tier_fn()
    _PLUGINS_BY_SCORE_TYPE[plugin.score_type] = plugin
    _PLUGINS_BY_ID[plugin.plugin_id] = plugin
    return plugin


def clear_plugins() -> None:
    """Test helper — clears the in-process plugin registry."""
    _PLUGINS_BY_SCORE_TYPE.clear()
    _PLUGINS_BY_ID.clear()


def get_plugin(score_type: str) -> IndicatorPlugin | None:
    return _PLUGINS_BY_SCORE_TYPE.get(score_type)


def require_plugin(score_type: str) -> IndicatorPlugin:
    plugin = get_plugin(score_type)
    if plugin is None:
        raise PluginError(
            f"No scorer plugin installed for score.type={score_type!r}. "
            "Register an IndicatorPlugin before activating this bundle."
        )
    # Prove callables still resolve (import drift / uninstall)
    plugin.resolve_scorer()
    return plugin


def list_plugins() -> list[IndicatorPlugin]:
    return sorted(_PLUGINS_BY_SCORE_TYPE.values(), key=lambda p: p.plugin_id)


def dispatch_score(score_type: str) -> Callable[..., Any]:
    """Shared dispatch: score.type → reference scorer callable."""
    return require_plugin(score_type).resolve_scorer()


# Built-in plugins (SOFA + AKI). Imported for side-effect registration.
def _register_builtins() -> None:
    if _PLUGINS_BY_SCORE_TYPE:
        return
    register_plugin(
        IndicatorPlugin(
            plugin_id="sofa-deterioration",
            score_type="sofa",
            indicator="sofa-deterioration",
            signal_kind="risk",
            display_name="SOFA organ dysfunction",
            bundle_id="sepsis-sofa",
            clinical_concepts=(
                "respiration",
                "coagulation",
                "liver",
                "cardiovascular",
                "cns",
                "renal",
            ),
            codes=("2160-0", "718-7", "1975-2", "8480-6", "9269-2"),
            units=("mg/dL", "10^9/L", "mmHg", "ratio"),
            windows={"score": "point-in-time with forward-fill per replay policy"},
            eligibility="Encounter with usable Observation inputs",
            exclusions=("comfort_care", "already_on_sepsis_protocol"),
            missing_data_policy="partial_with_missing_components",
            resolution_rule="governance refractory + resolution_gap_minutes",
            scorer_module="eval.sofa.scoring",
            scorer_attr="compute_sofa_score",
            tier_module="eval.sofa.scoring",
            tier_attr="tier_for_score",
            runtime_impl={
                "python": "eval.sofa.scoring.compute_sofa_score",
                "java": "com.curie.sofa.scoring.SofaScorer",
                "flink_job": "com.curie.sofa.operators.SofaAlertFunction",
            },
            fixture_paths=(
                "eval/fixtures/golden/sofa_cases.v0.2.json",
                "eval/fixtures/golden/cross_runtime_parity.v1.json",
            ),
            notes="Absolute SOFA is sofa-deterioration, not a sepsis diagnosis.",
        )
    )
    register_plugin(
        IndicatorPlugin(
            plugin_id="aki-kdigo",
            score_type="aki_kdigo",
            indicator="aki",
            signal_kind="risk",
            display_name="AKI (KDIGO-inspired)",
            bundle_id="aki-kdigo",
            clinical_concepts=(
                "creatinine",
                "baseline_creatinine",
                "urine_output",
                "weight",
            ),
            codes=("2160-0", "9187-6"),
            units=("mg/dL", "mL", "mL/kg/h", "kg"),
            windows={
                "delta_cr": "48h",
                "ratio_cr": "7d",
                "urine": "6h/12h/24h covered windows",
            },
            eligibility="Creatinine and/or evaluable UO; not ESRD-only without RRT flag",
            exclusions=("esrd", "comfort_care", "already_on_aki_protocol"),
            missing_data_policy="partial_with_missing_components; no reassuring UO without weight",
            resolution_rule="governance refractory + resolution_gap_minutes",
            scorer_module="eval.aki.scoring",
            scorer_attr="compute_aki_score",
            tier_module="eval.aki.scoring",
            tier_attr="tier_for_aki_score",
            runtime_impl={
                "python": "eval.aki.timeline.evaluate_aki_timeline",
                "python_legacy": "eval.aki.scoring.compute_aki_score",
                "java": "com.curie.sofa.aki.AkiTimeline",
                "flink_job": "com.curie.sofa.aki.AkiAlertFunction",
            },
            fixture_paths=(
                "eval/fixtures/golden/aki_timeline_cases.v1.json",
                "eval/fixtures/golden/cross_runtime_parity.v1.json",
            ),
            notes="Stateful timelines in eval.aki.timeline (CURIE-009).",
        )
    )


_register_builtins()
