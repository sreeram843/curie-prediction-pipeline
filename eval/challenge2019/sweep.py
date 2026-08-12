"""Task 5: tune governance on training_setA, freeze winner, score training_setB.

Selection goals (from docs/challenge-2019-eval.md §4):
  Primary: governed_sensitivity ≥ naive_sensitivity − 0.10 (or ≥ 0.70 absolute)
  Co-primary burden: interruptive_reduction_ratio ≤ 0.25 (pages vs naive);
    falls back to alert_reduction_ratio when page gate is off
  Secondary: prefer lower interruptive_nna / governed_nna
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from eval.challenge2019.runner import run_challenge2019_eval
from eval.indicators.registry import load_rule_bundle
from eval.replay_harness.gov_profiles import PROFILES
from ingestion.adapters.challenge2019.loader import (
    iter_psv_paths,
    load_stay_hours,
    require_challenge2019_dir,
)

DEFAULT_FREEZE_PATH = (
    Path(__file__).resolve().parent / "frozen" / "p1_setA_winner.json"
)

# Per-process state for parallel candidate eval (set by _init_worker).
_WORKER: dict[str, Any] = {}


def _grid_around_balanced() -> list[dict[str, Any]]:
    """Small grid around balanced (page persist fixed; ``dual`` covers 60m)."""
    base = deepcopy(PROFILES["balanced"])
    out: list[dict[str, Any]] = []
    for persist in (0, 15, 30):
        for refractory in (60, 90, 120):
            for baseline in (True, False):
                knobs = deepcopy(base)
                knobs["trajectory_persistence_minutes"] = persist
                knobs["refractory_minutes"] = refractory
                knobs["baseline_enabled"] = baseline
                knobs["page_gate_enabled"] = True
                knobs["page_trajectory_persistence_minutes"] = 30
                knobs["candidate_id"] = (
                    f"grid_p{persist}_r{refractory}_b{int(baseline)}"
                )
                knobs["description"] = (
                    f"balanced-grid persist={persist} refractory={refractory} "
                    f"baseline={baseline}"
                )
                out.append(knobs)
    return out


def iter_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for name, meta in PROFILES.items():
        knobs = deepcopy(meta)
        knobs["candidate_id"] = name
        candidates.append(knobs)
    candidates.extend(_grid_around_balanced())
    return candidates


def meets_primary(metrics: dict[str, Any]) -> bool:
    det = metrics["detection"]
    ns = det.get("naive_sensitivity")
    gs = det.get("governed_sensitivity")
    if gs is None:
        return False
    if gs >= 0.70:
        return True
    if ns is None:
        return False
    return gs >= ns - 0.10


def burden_ratio(metrics: dict[str, Any], *, page_gate: bool) -> float:
    alerts = metrics["alerts"]
    if page_gate:
        return float(alerts.get("interruptive_reduction_ratio") or 0.0)
    return float(alerts.get("alert_reduction_ratio") or 0.0)


def meets_coprimary(metrics: dict[str, Any], *, page_gate: bool) -> bool:
    return burden_ratio(metrics, page_gate=page_gate) <= 0.25


def rank_key(candidate: dict[str, Any], metrics: dict[str, Any]) -> tuple:
    """Higher is better."""
    page_gate = bool(candidate.get("page_gate_enabled"))
    det = metrics["detection"]
    gs = det.get("governed_sensitivity") or 0.0
    nna = det.get("interruptive_nna") if page_gate else det.get("governed_nna")
    nna_v = float(nna) if nna is not None else 1e9
    burden = burden_ratio(metrics, page_gate=page_gate)
    return (
        int(meets_primary(metrics)),
        int(meets_coprimary(metrics, page_gate=page_gate)),
        -burden,  # lower burden better
        -nna_v,  # lower NNA better
        gs,  # higher sens better
    )


def load_cached_stays(
    root: Path,
    set_name: str,
    limit: int | None,
) -> list[list]:
    paths = list(iter_psv_paths(root, set_name=set_name))
    if limit is not None:
        paths = paths[:limit]
    stays: list[list] = []
    for path in paths:
        hours = load_stay_hours(path)
        if hours:
            stays.append(hours)
    return stays


def _init_worker(
    stays: list[list],
    base: Path,
    grace_hours: int,
    bootstrap_samples: int,
) -> None:
    _WORKER["stays"] = stays
    _WORKER["base"] = base
    _WORKER["grace_hours"] = grace_hours
    _WORKER["bootstrap_samples"] = bootstrap_samples


def _eval_candidate(knobs: dict[str, Any]) -> dict[str, Any]:
    report = run_challenge2019_eval(
        root=_WORKER["base"],
        set_name="training_setA",
        detection_grace_hours=_WORKER["grace_hours"],
        gov_knobs=knobs,
        bootstrap_samples=_WORKER["bootstrap_samples"],
        cached_stays=_WORKER["stays"],
    )
    page_gate = bool(knobs.get("page_gate_enabled"))
    return {
        "candidate_id": knobs["candidate_id"],
        "knobs": deepcopy(knobs),
        "metrics": {
            "alerts": report["alerts"],
            "detection": report["detection"],
            "cohort": report["cohort"],
        },
        "meets_primary": meets_primary(report),
        "meets_coprimary": meets_coprimary(report, page_gate=page_gate),
        "burden_ratio": burden_ratio(report, page_gate=page_gate),
        "rank": list(rank_key(knobs, report)),
    }


def default_jobs() -> int:
    cpus = os.cpu_count() or 1
    return max(1, cpus - 1)


def run_sweep(
    *,
    root: Path | None = None,
    limit: int | None = None,
    grace_hours: int = 6,
    bootstrap_samples: int = 0,
    jobs: int | None = None,
) -> dict[str, Any]:
    base = require_challenge2019_dir(root)
    load_rule_bundle("sepsis-sofa")
    stays = load_cached_stays(base, "training_setA", limit)
    candidates = iter_candidates()
    workers = default_jobs() if jobs is None else max(1, jobs)

    if workers == 1 or len(candidates) == 1:
        _init_worker(stays, base, grace_hours, bootstrap_samples)
        results = [_eval_candidate(knobs) for knobs in candidates]
    else:
        # fork: children inherit cached stays without re-pickling (Unix/macOS).
        ctx = get_context("fork")
        results: list[dict[str, Any]] = []
        with ProcessPoolExecutor(
            max_workers=min(workers, len(candidates)),
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(stays, base, grace_hours, bootstrap_samples),
        ) as pool:
            futures = [pool.submit(_eval_candidate, knobs) for knobs in candidates]
            for fut in as_completed(futures):
                results.append(fut.result())

    results.sort(key=lambda e: tuple(e["rank"]), reverse=True)
    winner = results[0]
    return {
        "tune_set": "training_setA",
        "stays_scored": len(stays),
        "detection_grace_hours": grace_hours,
        "n_candidates": len(results),
        "jobs": workers,
        "winner_id": winner["candidate_id"],
        "winner": winner,
        "candidates": results,
    }


def freeze_winner(sweep: dict[str, Any], path: Path) -> dict[str, Any]:
    w = sweep["winner"]
    knobs = deepcopy(w["knobs"])
    knobs.pop("candidate_id", None)
    payload = {
        "name": "p1_setA_winner",
        "candidate_id": w["candidate_id"],
        "source_set": "training_setA",
        "selected_at": datetime.now(tz=UTC).isoformat(),
        "goals": {
            "primary": "governed_sensitivity >= naive_sensitivity - 0.10 or >= 0.70",
            "coprimary_burden": "interruptive_reduction_ratio <= 0.25 (else alert_reduction)",
            "secondary": "prefer lower NNA then higher sensitivity",
        },
        "setA": {
            "stays_scored": sweep["stays_scored"],
            "meets_primary": w["meets_primary"],
            "meets_coprimary": w["meets_coprimary"],
            "burden_ratio": w["burden_ratio"],
            "metrics": w["metrics"],
        },
        "knobs": knobs,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return payload


def run_holdout(
    freeze_path: Path,
    *,
    root: Path | None = None,
    limit: int | None = None,
    grace_hours: int = 6,
    bootstrap_samples: int = 1000,
) -> dict[str, Any]:
    report = run_challenge2019_eval(
        root=root,
        limit=limit,
        set_name="training_setB",
        detection_grace_hours=grace_hours,
        gov_config_path=freeze_path,
        bootstrap_samples=bootstrap_samples,
    )
    page_gate = bool(report["gov_profile_meta"].get("page_gate_enabled"))
    report["holdout"] = {
        "set": "training_setB",
        "meets_primary": meets_primary(report),
        "meets_coprimary": meets_coprimary(report, page_gate=page_gate),
        "burden_ratio": burden_ratio(report, page_gate=page_gate),
        "goals_met": meets_primary(report)
        and meets_coprimary(report, page_gate=page_gate),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Challenge 2019 setA sweep → freeze → setB holdout"
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0, help="0 = all stays")
    parser.add_argument("--grace-hours", type=int, default=6)
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help=f"Parallel candidate workers (default {default_jobs()}; 1 = serial)",
    )
    parser.add_argument(
        "--freeze-out",
        type=Path,
        default=DEFAULT_FREEZE_PATH,
        help="Where to write frozen winner JSON",
    )
    parser.add_argument(
        "--sweep-json-out",
        type=Path,
        default=None,
        help="Optional full sweep report JSON",
    )
    parser.add_argument(
        "--holdout-json-out",
        type=Path,
        default=None,
        help="Optional setB holdout report JSON",
    )
    parser.add_argument(
        "--skip-holdout",
        action="store_true",
        help="Only sweep + freeze (no setB)",
    )
    parser.add_argument(
        "--bootstrap",
        type=int,
        default=1000,
        help="Bootstrap replicates on holdout (sweep uses 0)",
    )
    args = parser.parse_args(argv)
    limit = None if args.limit == 0 else args.limit
    jobs = default_jobs() if args.jobs is None else args.jobs

    print(f"Sweeping training_setA (limit={limit}, jobs={jobs})…")
    sweep = run_sweep(
        root=args.root,
        limit=limit,
        grace_hours=args.grace_hours,
        bootstrap_samples=0,
        jobs=jobs,
    )
    freeze = freeze_winner(sweep, args.freeze_out)
    print(
        f"Winner={sweep['winner_id']} primary={sweep['winner']['meets_primary']} "
        f"coprimary={sweep['winner']['meets_coprimary']} "
        f"burden={sweep['winner']['burden_ratio']:.4f}"
    )
    print(f"Froze {args.freeze_out}")

    if args.sweep_json_out:
        args.sweep_json_out.parent.mkdir(parents=True, exist_ok=True)
        args.sweep_json_out.write_text(json.dumps(sweep, indent=2))
        print(f"Wrote {args.sweep_json_out}")

    if args.skip_holdout:
        print(json.dumps({"freeze": freeze["name"], "winner": sweep["winner_id"]}, indent=2))
        return 0

    print("Scoring holdout training_setB…")
    holdout = run_holdout(
        args.freeze_out,
        root=args.root,
        limit=limit,
        grace_hours=args.grace_hours,
        bootstrap_samples=args.bootstrap,
    )
    summary = {
        "winner_id": sweep["winner_id"],
        "freeze_path": str(args.freeze_out),
        "setA": freeze["setA"],
        "setB_holdout": {
            "stays_scored": holdout["stays_scored"],
            "meets_primary": holdout["holdout"]["meets_primary"],
            "meets_coprimary": holdout["holdout"]["meets_coprimary"],
            "goals_met": holdout["holdout"]["goals_met"],
            "burden_ratio": holdout["holdout"]["burden_ratio"],
            "alerts": holdout["alerts"],
            "detection": holdout["detection"],
            "bootstrap": holdout.get("bootstrap"),
        },
    }
    print(json.dumps(summary, indent=2))
    if args.holdout_json_out:
        args.holdout_json_out.parent.mkdir(parents=True, exist_ok=True)
        args.holdout_json_out.write_text(json.dumps(holdout, indent=2))
        print(f"Wrote {args.holdout_json_out}")
    return 0 if holdout["holdout"]["goals_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
