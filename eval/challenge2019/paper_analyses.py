"""Publication analyses on Challenge 2019 (comparators, ablation, miss, CIs).

Tune/selection remains frozen on setA. This module only *evaluates* setB
(or a requested split) and writes aggregate sidecars — never retunes knobs.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.challenge2019.ablation import (
    ablation_variants,
    knob_signature,
    load_frozen_knobs,
)
from eval.challenge2019.comparators import run_comparators
from eval.challenge2019.miss_analysis import build_replay_miss_table
from eval.challenge2019.runner import run_challenge2019_eval
from eval.challenge2019.sweep import load_cached_stays
from eval.replay_harness.gov_profiles import PROFILES
from ingestion.adapters.challenge2019.loader import require_challenge2019_dir

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
WINNER_PATH = FROZEN_DIR / "p1_setA_winner.json"


def _metrics_card(report: dict[str, Any]) -> dict[str, Any]:
    det = report["detection"]
    alerts = report["alerts"]
    boot = report.get("bootstrap") or {}
    boot_metrics = boot.get("metrics") or {}
    return {
        "stays_scored": report.get("stays_scored"),
        "governed_sensitivity": det.get("governed_sensitivity"),
        "interruptive_sensitivity": det.get("interruptive_sensitivity"),
        "naive_sensitivity": det.get("naive_sensitivity"),
        "interruptive_reduction_ratio": alerts.get("interruptive_reduction_ratio"),
        "interruptive_nna": det.get("interruptive_nna"),
        "naive_total": alerts.get("naive_total"),
        "governed_total": alerts.get("governed_total"),
        "interruptive_total": alerts.get("interruptive_total"),
        "mean_lead_hours_in_window": det.get("mean_lead_hours_governed_in_window"),
        "bootstrap": {
            "n_boot": boot.get("n_boot"),
            "seed": boot.get("seed"),
            "governed_sensitivity": boot_metrics.get("detection.governed_sensitivity"),
            "interruptive_sensitivity": boot_metrics.get(
                "detection.interruptive_sensitivity"
            ),
            "interruptive_nna": boot_metrics.get("detection.interruptive_nna"),
            "interruptive_reduction_ratio": boot_metrics.get(
                "alerts.interruptive_reduction_ratio"
            ),
            "mean_lead_hours_governed_in_window": boot_metrics.get(
                "detection.mean_lead_hours_governed_in_window"
            ),
        }
        if boot_metrics
        else None,
    }


def run_holdout_with_rows(
    *,
    stays: list[list],
    bootstrap_samples: int,
    root: Path,
) -> dict[str, Any]:
    return run_challenge2019_eval(
        root=root,
        set_name="training_setB",
        gov_config_path=WINNER_PATH,
        bootstrap_samples=bootstrap_samples,
        cached_stays=stays,
        include_stay_rows=True,
    )


def run_ablation(
    *,
    stays: list[list],
    root: Path,
) -> dict[str, Any]:
    primary_sig = knob_signature(load_frozen_knobs())
    rows_out: list[dict[str, Any]] = []
    for name, knobs in ablation_variants():
        report = run_challenge2019_eval(
            root=root,
            gov_knobs=knobs,
            bootstrap_samples=0,
            cached_stays=stays,
        )
        card = _metrics_card(report)
        card["id"] = name
        card["null_vs_primary"] = knob_signature(knobs) == primary_sig and name != (
            "primary_operating_point"
        )
        card["knobs"] = {
            k: knobs.get(k)
            for k in (
                "trajectory_persistence_minutes",
                "min_crossings",
                "baseline_enabled",
                "refractory_minutes",
                "page_gate_enabled",
                "page_min_crossings",
                "page_trajectory_persistence_minutes",
            )
        }
        rows_out.append(card)
    return {
        "schema_version": "1.0.0",
        "cohort": "training_setB",
        "operating_point": str(WINNER_PATH.relative_to(Path(__file__).resolve().parents[2])),
        "notes": [
            "Ablation evaluates the frozen setA winner on setB; knobs are not reselected.",
            "drop_baseline is a null ablation: the winner already has baseline_enabled=false.",
            "drop_persistence zeros watch persist (already 0) and page persist (30 → 0).",
        ],
        "variants": rows_out,
    }


def run_named_profile_pareto(
    *,
    stays: list[list],
    root: Path,
) -> dict[str, Any]:
    """Named gov profiles + frozen winner on the requested stays (typically setA)."""
    winner_knobs = load_frozen_knobs()
    winner_knobs["candidate_id"] = "grid_p0_r90_b0"
    candidates: list[dict[str, Any]] = []
    for name, meta in PROFILES.items():
        knobs = deepcopy(meta)
        knobs["candidate_id"] = name
        candidates.append(knobs)
    candidates.append(winner_knobs)

    points: list[dict[str, Any]] = []
    for knobs in candidates:
        report = run_challenge2019_eval(
            root=root,
            gov_knobs=knobs,
            bootstrap_samples=0,
            cached_stays=stays,
        )
        det = report["detection"]
        alerts = report["alerts"]
        cid = str(knobs["candidate_id"])
        points.append(
            {
                "candidate_id": cid,
                "governed_sensitivity": det.get("governed_sensitivity"),
                "interruptive_reduction_ratio": alerts.get(
                    "interruptive_reduction_ratio"
                ),
                "interruptive_sensitivity": det.get("interruptive_sensitivity"),
                "selected": cid == "grid_p0_r90_b0",
            }
        )
    return {
        "schema_version": "1.0.0",
        "source": "named_profiles_plus_frozen_winner",
        "notes": [
            "Not the full 23-candidate setA grid. The selected point remains "
            "grid_p0_r90_b0 from the original sweep. This figure places that "
            "point among named profiles.",
        ],
        "points": points,
    }


def run_paper_analyses(
    *,
    root: Path | None = None,
    limit: int | None = None,
    bootstrap_samples: int = 1000,
    skip_pareto: bool = False,
    skip_ablation: bool = False,
) -> dict[str, Any]:
    base = require_challenge2019_dir(root)
    set_b = load_cached_stays(base, "training_setB", limit)

    holdout = run_holdout_with_rows(
        stays=set_b, bootstrap_samples=bootstrap_samples, root=base
    )
    stay_rows = holdout.pop("stay_rows")
    miss = build_replay_miss_table(
        stay_rows,
        rule_config_hash=(holdout.get("rule_bundle") or {}).get("content_hash"),
    )
    comparators = run_comparators(set_b)
    ablation = None if skip_ablation else run_ablation(stays=set_b, root=base)

    pareto = None
    if not skip_pareto:
        set_a = load_cached_stays(base, "training_setA", limit)
        pareto = run_named_profile_pareto(stays=set_a, root=base)
        pareto["split"] = "training_setA"
        pareto["stays_scored"] = len(set_a)

    holdout_card = _metrics_card(holdout)
    generated_at = datetime.now(tz=UTC).isoformat()
    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "disclaimer": (
            "Retrospective Challenge 2019 analyses only. Not clinical validation. "
            "setB is not retuned."
        ),
        "limits": {"stays": limit},
        "holdout": holdout_card,
        "comparators": comparators,
        "ablation": ablation,
        "miss_analysis": miss,
        "pareto": pareto,
        "holdout_sidecar": {
            "schema_version": "2.0.0",
            "detection_mode_id": "window_m12_p6",
            "cohort": "training_setB",
            "n_stays": holdout_card["stays_scored"],
            "operating_point": "eval/challenge2019/frozen/p1_setA_winner.json",
            "detection": {
                "governed_sensitivity": holdout_card["governed_sensitivity"],
                "interruptive_sensitivity": holdout_card["interruptive_sensitivity"],
                "interruptive_nna": holdout_card["interruptive_nna"],
                "mean_lead_hours_in_window": holdout_card["mean_lead_hours_in_window"],
            },
            "bootstrap": holdout_card["bootstrap"],
            "notes": [
                "Primary detection window: any alert in [onset-12h, onset+6h].",
                "Stay-level percentile bootstrap, seed 42.",
                "Does not replace v1 point estimates; v2 adds intervals.",
            ],
        },
    }


def write_frozen(report: dict[str, Any], *, frozen_dir: Path = FROZEN_DIR) -> None:
    frozen_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "holdout_primary_window_m12_p6.v2.json": report["holdout_sidecar"],
        "comparators_setB_window_m12_p6.v1.json": report["comparators"],
        "ablation_setB_window_m12_p6.v1.json": report["ablation"],
        "miss_analysis.v2.json": report["miss_analysis"],
        "pareto_named_profiles.v1.json": report["pareto"],
    }
    for name, payload in mapping.items():
        if payload is None:
            continue
        (frozen_dir / name).write_text(json.dumps(payload, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Challenge 2019 paper analyses (setB eval + optional setA profiles)"
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0, help="0 = all stays")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--skip-pareto", action="store_true")
    parser.add_argument("--skip-ablation", action="store_true")
    parser.add_argument("--write-frozen", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    limit = None if args.limit == 0 else args.limit
    report = run_paper_analyses(
        root=args.root,
        limit=limit,
        bootstrap_samples=args.bootstrap,
        skip_pareto=args.skip_pareto,
        skip_ablation=args.skip_ablation,
    )
    summary = {
        "holdout": report["holdout"],
        "comparators": [
            {"id": c["id"], "metrics": c["metrics"]}
            for c in (report["comparators"] or {}).get("comparators") or []
        ],
        "ablation_ids": [
            v["id"] for v in ((report["ablation"] or {}).get("variants") or [])
        ],
        "miss_n": (report["miss_analysis"] or {}).get("n_false_negatives"),
        "pareto_points": len((report["pareto"] or {}).get("points") or []),
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Wrote {args.json_out}")
    if args.write_frozen:
        write_frozen(report)
        print(f"Wrote frozen sidecars under {FROZEN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
