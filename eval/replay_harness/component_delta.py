"""Component-delta helpers for dual-lane page gates (CURIE-032)."""

from __future__ import annotations

from typing import Any


def component_points_from_alert(alert: dict[str, Any]) -> dict[str, int]:
    """Extract {component_name: points} from a scored alert payload."""
    out: dict[str, int] = {}
    breakdown = alert.get("component_breakdown") or alert.get("components") or []
    if isinstance(breakdown, dict):
        for name, raw in breakdown.items():
            if isinstance(raw, dict):
                pts = raw.get("points", raw.get("score"))
            else:
                pts = raw
            if pts is None:
                continue
            out[str(name)] = int(pts)
        return out
    if isinstance(breakdown, list):
        for item in breakdown:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("component")
            pts = item.get("points", item.get("score"))
            if name is None or pts is None:
                continue
            out[str(name)] = int(pts)
    return out


def compute_component_deltas(
    current: dict[str, int],
    prior: dict[str, int] | None,
) -> dict[str, Any]:
    """Return newly worsened components and per-component deltas vs prior vector."""
    prior = prior or {}
    deltas: dict[str, int] = {}
    newly_worsened: list[str] = []
    for name, pts in sorted(current.items()):
        prev = int(prior.get(name, 0))
        delta = int(pts) - prev
        deltas[name] = delta
        if delta > 0:
            newly_worsened.append(name)
    return {
        "component_points": dict(current),
        "component_deltas": deltas,
        "newly_worsened_components": newly_worsened,
        "newly_worsened_count": len(newly_worsened),
        "max_component_delta": max(deltas.values()) if deltas else 0,
    }
