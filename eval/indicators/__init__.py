"""Indicator plugins (rule-bundle driven) + CURIE-011 SDK."""

from eval.indicators.plugin import (
    IndicatorPlugin,
    PluginError,
    dispatch_score,
    list_plugins,
    register_plugin,
    require_plugin,
)
from eval.indicators.registry import (
    list_indicators,
    load_rule_bundle,
    validate_activation,
)

__all__ = [
    "IndicatorPlugin",
    "PluginError",
    "dispatch_score",
    "list_indicators",
    "list_plugins",
    "load_rule_bundle",
    "register_plugin",
    "require_plugin",
    "validate_activation",
]
