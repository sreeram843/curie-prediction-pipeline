"""SetB ablation of frozen governance knobs (evaluation only — never retune)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

FROZEN_WINNER = Path(__file__).resolve().parent / "frozen" / "p1_setA_winner.json"

ABLATION_ORDER = (
    "primary_operating_point",
    "drop_baseline",
    "drop_persistence",
    "drop_crossings",
    "drop_refractory",
    "drop_page_gate",
)


def load_frozen_knobs(path: Path | None = None) -> dict[str, Any]:
    data = json.loads((path or FROZEN_WINNER).read_text())
    knobs = deepcopy(data.get("knobs") or {})
    knobs["resolved_bundle"] = data.get("resolved_bundle")
    knobs["candidate_id"] = data.get("candidate_id")
    knobs["description"] = knobs.get("description") or data.get("name")
    return knobs


_KNOB_KEYS = (
    "trajectory_persistence_minutes",
    "min_crossings",
    "baseline_enabled",
    "baseline_delta_threshold",
    "baseline_lookback_hours",
    "refractory_minutes",
    "min_components_required",
    "naive_threshold",
    "page_gate_enabled",
    "page_min_crossings",
    "page_trajectory_persistence_minutes",
    "page_min_score_delta",
    "page_min_positive_components",
)


def knob_signature(knobs: dict[str, Any]) -> tuple:
    return tuple(knobs.get(k) for k in _KNOB_KEYS)


def ablation_variants(base: dict[str, Any] | None = None) -> list[tuple[str, dict[str, Any]]]:
    knobs = deepcopy(base or load_frozen_knobs())
    variants: list[tuple[str, dict[str, Any]]] = []

    primary = deepcopy(knobs)
    primary["candidate_id"] = "primary_operating_point"
    variants.append(("primary_operating_point", primary))

    drop_baseline = deepcopy(knobs)
    drop_baseline["baseline_enabled"] = False
    drop_baseline["candidate_id"] = "drop_baseline"
    variants.append(("drop_baseline", drop_baseline))

    drop_persist = deepcopy(knobs)
    drop_persist["trajectory_persistence_minutes"] = 0
    drop_persist["page_trajectory_persistence_minutes"] = 0
    drop_persist["candidate_id"] = "drop_persistence"
    variants.append(("drop_persistence", drop_persist))

    drop_x = deepcopy(knobs)
    drop_x["min_crossings"] = 1
    drop_x["page_min_crossings"] = 1
    drop_x["candidate_id"] = "drop_crossings"
    variants.append(("drop_crossings", drop_x))

    drop_ref = deepcopy(knobs)
    drop_ref["refractory_minutes"] = 0
    drop_ref["candidate_id"] = "drop_refractory"
    variants.append(("drop_refractory", drop_ref))

    drop_page = deepcopy(knobs)
    drop_page["page_gate_enabled"] = False
    drop_page["candidate_id"] = "drop_page_gate"
    variants.append(("drop_page_gate", drop_page))

    return variants
