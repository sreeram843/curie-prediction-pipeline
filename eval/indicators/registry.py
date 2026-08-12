"""Indicator plugin registry — maps rule bundle score.type → scorer.

Phase 3 proof: adding AKI is a new scorer + rule bundle entry, not a platform rewrite.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eval.indicators.plugin import (
    PluginError,
    get_plugin,
    require_plugin,
)
from eval.indicators.semver import compare_semver, parse_semver

if TYPE_CHECKING:
    from eval.replay_harness.governance import GovernanceConfig

BUNDLES_DIR = (
    Path(__file__).resolve().parents[2] / "streaming" / "rule-registry" / "bundles"
)
ACTIVATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "streaming"
    / "rule-registry"
    / "activation.json"
)

ScorerFn = Callable[..., Any]

_FILENAME_RE = re.compile(r"^(?P<id>.+)\.v(?P<ver>\d+\.\d+\.\d+)\.json$")


class RuleBundleError(ValueError):
    """Invalid or ambiguous rule-bundle resolution."""


def content_hash(bundle: dict[str, Any]) -> str:
    """Stable SHA-256 of bundle JSON (sorted keys, no whitespace variance)."""
    payload = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_activation(path: Path | None = None) -> dict[str, str]:
    activation_path = path or ACTIVATION_PATH
    data = json.loads(activation_path.read_text())
    active = data.get("active") or {}
    if not isinstance(active, dict) or not active:
        raise RuleBundleError(f"Activation manifest missing active map: {activation_path}")
    return {str(k): str(v) for k, v in active.items()}


def _bundle_paths(bundle_id: str) -> list[tuple[str, Path]]:
    """Return (version, path) pairs for a bundle_id, sorted by semver ascending."""
    found: dict[str, Path] = {}
    for path in BUNDLES_DIR.glob(f"{bundle_id}.v*.json"):
        m = _FILENAME_RE.match(path.name)
        if not m or m.group("id") != bundle_id:
            continue
        ver = m.group("ver")
        parse_semver(ver)
        if ver in found:
            raise RuleBundleError(
                f"Duplicate version {ver} for {bundle_id}: {found[ver]} and {path}"
            )
        found[ver] = path
    return sorted(found.items(), key=lambda kv: parse_semver(kv[0]))


def _validate_bundle(
    data: dict[str, Any],
    *,
    path: Path,
    expected_version: str,
    require_scorer: bool = True,
) -> None:
    for key in ("bundle_id", "version", "indicator", "score"):
        if key not in data:
            raise RuleBundleError(f"Bundle {path} missing required field {key!r}")
    parse_semver(str(data["version"]))
    if str(data["version"]) != expected_version:
        raise RuleBundleError(
            f"Bundle {path} version {data['version']!r} != filename version "
            f"{expected_version!r}"
        )
    score = data.get("score") or {}
    if not score.get("type"):
        raise RuleBundleError(f"Bundle {path} score.type is required")
    if require_scorer:
        try:
            require_plugin(str(score["type"]))
        except PluginError as exc:
            raise RuleBundleError(str(exc)) from exc


def resolve_bundle_version(
    bundle_id: str,
    version: str | None = None,
    *,
    allow_latest: bool | None = None,
) -> str:
    """Resolve which version to load.

    - Explicit version string (not ``latest``) is returned after validation.
    - ``None`` / ``latest`` uses the activation manifest (dev convenience).
    - Production: set ``CURIE_REQUIRE_EXPLICIT_RULE_VERSION=1`` or pass
      ``allow_latest=False`` to reject implicit latest.
    """
    if allow_latest is None:
        allow_latest = os.environ.get(
            "CURIE_REQUIRE_EXPLICIT_RULE_VERSION", ""
        ).lower() not in ("1", "true", "yes")

    if version is None or version == "latest":
        if not allow_latest:
            raise RuleBundleError(
                f"Explicit rule version required for {bundle_id!r} "
                "(set version= or unset CURIE_REQUIRE_EXPLICIT_RULE_VERSION)"
            )
        active = load_activation()
        if bundle_id not in active:
            raise RuleBundleError(
                f"No active version for {bundle_id!r} in {ACTIVATION_PATH.name}"
            )
        return active[bundle_id]

    try:
        parse_semver(version)
    except ValueError as exc:
        raise RuleBundleError(str(exc)) from exc
    return version


def load_rule_bundle(
    bundle_id: str,
    version: str | None = None,
    *,
    allow_latest: bool | None = None,
    include_hash: bool = True,
    require_scorer: bool = True,
) -> dict[str, Any]:
    """Load a versioned rule bundle.

    Default ``version=None`` resolves through ``activation.json`` (semver-aware),
    never by lexicographic filename sort.

    When ``require_scorer=True`` (default), ``score.type`` must map to a
    registered :class:`~eval.indicators.plugin.IndicatorPlugin` (CURIE-011).
    """
    resolved = resolve_bundle_version(bundle_id, version, allow_latest=allow_latest)
    path = BUNDLES_DIR / f"{bundle_id}.v{resolved}.json"
    if not path.exists():
        available = [v for v, _ in _bundle_paths(bundle_id)]
        raise FileNotFoundError(
            f"No bundle {bundle_id} v{resolved} in {BUNDLES_DIR} "
            f"(available: {available})"
        )
    data = json.loads(path.read_text())
    _validate_bundle(
        data, path=path, expected_version=resolved, require_scorer=require_scorer
    )
    if include_hash:
        data = dict(data)
        data["content_hash"] = content_hash(
            {k: v for k, v in data.items() if k != "content_hash"}
        )
    return data


def validate_activation(path: Path | None = None) -> dict[str, Any]:
    """Fail if any active bundle references an uninstalled score.type."""
    active = load_activation(path)
    report: dict[str, Any] = {"active": {}, "ok": True}
    errors: list[str] = []
    for bundle_id, version in sorted(active.items()):
        try:
            bundle = load_rule_bundle(
                bundle_id, version, allow_latest=False, require_scorer=True
            )
            score_type = str((bundle.get("score") or {}).get("type"))
            plugin = require_plugin(score_type)
            report["active"][bundle_id] = {
                "version": version,
                "score_type": score_type,
                "plugin_id": plugin.plugin_id,
                "scorer_installed": True,
                "runtime_impl": dict(plugin.runtime_impl),
            }
        except (RuleBundleError, PluginError, FileNotFoundError, ValueError) as exc:
            report["ok"] = False
            errors.append(f"{bundle_id}@{version}: {exc}")
            report["active"][bundle_id] = {
                "version": version,
                "scorer_installed": False,
                "error": str(exc),
            }
    report["errors"] = errors
    if not report["ok"]:
        raise RuleBundleError(
            "Activation failed — unsupported or missing scorers:\n"
            + "\n".join(errors)
        )
    return report


def list_indicators(
    *,
    installed_only: bool = True,
) -> list[dict[str, Any]]:
    """List rule-bundle indicators.

    When ``installed_only`` is True (default), only bundles whose ``score.type``
    has a registered plugin are returned — listing proves a scorer is installed.
    """
    out: list[dict[str, Any]] = []
    seen: dict[str, set[str]] = {}
    for path in sorted(BUNDLES_DIR.glob("*.json")):
        m = _FILENAME_RE.match(path.name)
        if not m:
            continue
        data = json.loads(path.read_text())
        bid = str(data.get("bundle_id") or m.group("id"))
        ver = str(data.get("version") or m.group("ver"))
        parse_semver(ver)
        seen.setdefault(bid, set())
        if ver in seen[bid]:
            raise RuleBundleError(f"Duplicate version {ver} for {bid}")
        seen[bid].add(ver)
        score_type = str((data.get("score") or {}).get("type") or "")
        plugin = get_plugin(score_type) if score_type else None
        if installed_only and plugin is None:
            continue
        entry: dict[str, Any] = {
            "bundle_id": bid,
            "version": ver,
            "indicator": data["indicator"],
            "score_type": score_type,
            "path": str(path),
            "content_hash": content_hash(data),
            "scorer_installed": plugin is not None,
        }
        if plugin is not None:
            entry["plugin_id"] = plugin.plugin_id
            entry["signal_kind"] = plugin.signal_kind
            entry["runtime_impl"] = dict(plugin.runtime_impl)
            entry["scorer"] = f"{plugin.scorer_module}.{plugin.scorer_attr}"
        out.append(entry)
    out.sort(key=lambda r: (r["bundle_id"], parse_semver(r["version"])))
    return out


def max_version(versions: list[str]) -> str:
    if not versions:
        raise RuleBundleError("No versions")
    return max(versions, key=parse_semver)


def is_newer_version(candidate: str, current: str) -> bool:
    return compare_semver(candidate, current) > 0


def governance_config_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Extract governance knobs for the shared Python/Java governance mirror.

    Defaults match ``GovernancePolicy.Config`` / ``GovernanceConfig`` when a field
    is absent from the JSON (CURIE-005 parity).
    """
    g = bundle.get("governance") or {}
    traj = g.get("trajectory") or {}
    base = g.get("baseline") or {}
    dedup = g.get("dedup") or {}
    supp = g.get("suppression") or {}
    tier = g.get("tiering") or {}
    page = g.get("page_gate") or {}
    quality = g.get("quality_gate") or {}
    default_flags = {"comfort_care", "already_on_sepsis_protocol"}
    flags = set(supp.get("flags") or default_flags)
    interruptive = set(tier.get("interruptive_tiers") or ["urgent", "critical"])
    passive = set(tier.get("passive_tiers") or ["watch"])
    high = page.get("high_actionability_components") or []
    return {
        "trajectory_persistence_minutes": int(traj.get("min_persistence_minutes", 30)),
        "min_crossings": int(traj.get("min_crossings", 2)),
        "baseline_enabled": bool(base.get("enabled", True)),
        "baseline_delta_threshold": int(base.get("delta_threshold", 2)),
        "baseline_lookback_hours": int(base.get("lookback_hours", 24)),
        "refractory_minutes": int(dedup.get("refractory_minutes", 120)),
        "resolution_gap_minutes": int(dedup.get("resolution_gap_minutes", 60)),
        "suppression_flags": flags,
        "interruptive_tiers": interruptive,
        "passive_tiers": passive,
        "page_gate_enabled": bool(page.get("enabled", False)),
        "page_min_crossings": int(page.get("min_crossings", 2)),
        "page_trajectory_persistence_minutes": int(
            page.get("trajectory_persistence_minutes", 30)
        ),
        "page_min_score_delta": int(page.get("min_score_delta", 1)),
        "page_min_positive_components": int(page.get("min_positive_components", 0)),
        "page_min_newly_worsened_components": int(
            page.get("min_newly_worsened_components", 0)
        ),
        "page_min_component_delta": int(page.get("min_component_delta", 0)),
        "page_high_actionability_components": tuple(str(x) for x in high),
        "quality_gate_enabled": bool(quality.get("enabled", False)),
        "quality_max_data_age_minutes": int(quality.get("max_data_age_minutes", 0)),
        "quality_require_critical_inputs": bool(
            quality.get("require_critical_inputs", False)
        ),
        "quality_reject_invalid": bool(quality.get("reject_invalid", True)),
        "quality_reject_contradictory": bool(quality.get("reject_contradictory", True)),
        "quality_require_trusted_source": bool(
            quality.get("require_trusted_source", False)
        ),
        "quality_reject_ood": bool(quality.get("reject_ood", False)),
    }


def governance_dataclass_from_bundle(
    bundle: dict[str, Any],
    *,
    overrides: dict[str, Any] | None = None,
) -> GovernanceConfig:
    """Build ``GovernanceConfig`` from a rule bundle, with optional scenario overrides."""
    from eval.replay_harness.governance import GovernanceConfig

    knobs = governance_config_from_bundle(bundle)
    if overrides:
        fields = GovernanceConfig.__dataclass_fields__
        for key, value in overrides.items():
            if key not in fields:
                raise KeyError(f"Unknown governance override {key!r}")
            knobs[key] = value
    return GovernanceConfig(
        trajectory_persistence_minutes=knobs["trajectory_persistence_minutes"],
        min_crossings=knobs["min_crossings"],
        baseline_enabled=knobs["baseline_enabled"],
        baseline_delta_threshold=knobs["baseline_delta_threshold"],
        baseline_lookback_hours=knobs["baseline_lookback_hours"],
        refractory_minutes=knobs["refractory_minutes"],
        resolution_gap_minutes=knobs["resolution_gap_minutes"],
        suppression_flags=set(knobs["suppression_flags"]),
        interruptive_tiers=set(knobs["interruptive_tiers"]),
        passive_tiers=set(knobs["passive_tiers"]),
        page_gate_enabled=knobs["page_gate_enabled"],
        page_min_crossings=knobs["page_min_crossings"],
        page_trajectory_persistence_minutes=knobs[
            "page_trajectory_persistence_minutes"
        ],
        page_min_score_delta=knobs["page_min_score_delta"],
        page_min_positive_components=knobs["page_min_positive_components"],
        page_min_newly_worsened_components=knobs["page_min_newly_worsened_components"],
        page_min_component_delta=knobs["page_min_component_delta"],
        page_high_actionability_components=tuple(
            knobs["page_high_actionability_components"]
        ),
        quality_gate_enabled=knobs["quality_gate_enabled"],
        quality_max_data_age_minutes=knobs["quality_max_data_age_minutes"],
        quality_require_critical_inputs=knobs["quality_require_critical_inputs"],
        quality_reject_invalid=knobs["quality_reject_invalid"],
        quality_reject_contradictory=knobs["quality_reject_contradictory"],
        quality_require_trusted_source=knobs["quality_require_trusted_source"],
        quality_reject_ood=knobs["quality_reject_ood"],
    )
