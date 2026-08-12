"""Task 6: detection-window robustness across definitions.

Score stays once per config (frozen + comparison profiles), then re-summarize under
grace 0/6/12h, early-only, and ±12h window without re-scoring.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path
from typing import Any

from eval.challenge2019.bootstrap import DETECTION_MODES, summarize_stay_metrics
from eval.challenge2019.runner import _replay_stay
from eval.challenge2019.sweep import DEFAULT_FREEZE_PATH, default_jobs, load_cached_stays
from eval.indicators.registry import load_rule_bundle
from eval.replay_harness.gov_profiles import PROFILES, apply_gov_knobs, apply_gov_profile
from ingestion.adapters.challenge2019.loader import require_challenge2019_dir

_RANK_PROFILES = ("strict", "accuracy", "dual", "balanced")
_WORKER: dict[str, Any] = {}


def _replay_rows(
    *,
    stays: list[list],
    gov_profile: str | None = None,
    gov_config_path: Path | None = None,
) -> tuple[str, list[dict]]:
    bundle_in = load_rule_bundle("sepsis-sofa")
    if gov_config_path is not None:
        frozen = json.loads(Path(gov_config_path).read_text())
        knobs = frozen.get("knobs") or frozen
        bundle, gov_config, _meta = apply_gov_knobs(bundle_in, knobs)
        label = str(frozen.get("candidate_id") or "frozen")
    else:
        assert gov_profile is not None
        bundle, gov_config, _meta = apply_gov_profile(bundle_in, gov_profile)
        label = gov_profile
    min_components = int(
        (bundle.get("score") or {}).get("min_components_required") or 3
    )
    rows = [
        _replay_stay(
            hours,
            bundle=bundle,
            gov_config=gov_config,
            min_components_required=min_components,
        )
        for hours in stays
    ]
    return label, rows


def summarize_modes(rows: list[dict]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in DETECTION_MODES:
        summary = summarize_stay_metrics(rows, detection_mode=mode)
        det = summary["detection"]
        ns = det["naive_sensitivity"]
        gs = det["governed_sensitivity"]
        out[mode] = {
            "naive_sensitivity": ns,
            "governed_sensitivity": gs,
            "interruptive_sensitivity": det["interruptive_sensitivity"],
            "naive_tp": det["naive_tp"],
            "governed_tp": det["governed_tp"],
            "interruptive_tp": det["interruptive_tp"],
            "delta_gov_minus_naive_pp": (
                None if ns is None or gs is None else (gs - ns) * 100.0
            ),
        }
    return out


def rank_profiles(mode_tables: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    ranks: dict[str, list[str]] = {}
    for mode in DETECTION_MODES:
        scored = []
        for label, modes in mode_tables.items():
            gs = modes[mode].get("governed_sensitivity")
            if gs is None:
                continue
            scored.append((gs, label))
        scored.sort(reverse=True)
        ranks[mode] = [label for _gs, label in scored]
    return ranks


def ranking_stable(ranks: dict[str, list[str]], *, reference: str = "window_m12_p6") -> bool:
    ref = ranks.get(reference)
    if not ref:
        return False
    return all(order == ref for order in ranks.values())


def _init_worker(stays: list[list]) -> None:
    _WORKER["stays"] = stays


def _eval_config(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    label, rows = _replay_rows(
        stays=_WORKER["stays"],
        gov_profile=spec.get("gov_profile"),
        gov_config_path=Path(spec["gov_config_path"])
        if spec.get("gov_config_path")
        else None,
    )
    # Prefer stable outer label (e.g. "frozen") over candidate_id inside file.
    return spec["label"], summarize_modes(rows)


def run_robustness(
    *,
    root: Path | None = None,
    set_name: str = "training_setB",
    limit: int | None = None,
    freeze_path: Path = DEFAULT_FREEZE_PATH,
    include_profiles: bool = True,
    jobs: int | None = None,
) -> dict[str, Any]:
    base = require_challenge2019_dir(root)
    stays = load_cached_stays(base, set_name, limit)

    specs: list[dict[str, Any]] = [
        {"label": "frozen", "gov_config_path": str(freeze_path), "gov_profile": None},
    ]
    if include_profiles:
        for name in _RANK_PROFILES:
            if name in PROFILES:
                specs.append(
                    {"label": name, "gov_config_path": None, "gov_profile": name}
                )

    workers = default_jobs() if jobs is None else max(1, jobs)
    by_label: dict[str, dict[str, Any]] = {}

    if workers == 1 or len(specs) == 1:
        _init_worker(stays)
        for spec in specs:
            label, modes = _eval_config(spec)
            by_label[label] = modes
    else:
        ctx = get_context("fork")
        with ProcessPoolExecutor(
            max_workers=min(workers, len(specs)),
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(stays,),
        ) as pool:
            futs = [pool.submit(_eval_config, spec) for spec in specs]
            for fut in as_completed(futs):
                label, modes = fut.result()
                by_label[label] = modes

    ranks = rank_profiles(by_label)
    stable = ranking_stable(ranks)

    return {
        "set": set_name,
        "stays_scored": len(stays),
        "freeze_path": str(freeze_path),
        "jobs": workers,
        "detection_modes": list(DETECTION_MODES),
        "by_config": by_label,
        "ranking_by_mode": ranks,
        "ranking_stable_vs_primary": stable,
        "ranking_stable_vs_grace_6": stable,
        "notes": [
            "PRIMARY window_m12_p6: any alert in [label_start-12h, label_start+6h] (CURIE-004)",
            "grace_N: legacy first alert ICULOS <= onset + N (sensitivity analysis)",
            "early_only: first alert ICULOS < onset",
            "window_pm12: any alert hour in [onset-12, onset+12]",
            "Challenge SepsisLabel begins ~6h before clinical onset (label_start).",
            "Alert totals unchanged across modes; only TP/sensitivity re-defined.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Challenge 2019 detection-window robustness report"
    )
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--set", dest="set_name", default="training_setB")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE_PATH)
    parser.add_argument(
        "--frozen-only",
        action="store_true",
        help="Skip profile ranking comparison (faster)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help=f"Parallel config workers (default {default_jobs()})",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    limit = None if args.limit == 0 else args.limit
    jobs = 1 if args.frozen_only else (default_jobs() if args.jobs is None else args.jobs)

    report = run_robustness(
        root=args.root,
        set_name=args.set_name,
        limit=limit,
        freeze_path=args.freeze,
        include_profiles=not args.frozen_only,
        jobs=jobs,
    )
    frozen = report["by_config"].get("frozen", {})
    compact = {
        "set": report["set"],
        "stays_scored": report["stays_scored"],
        "ranking_stable_vs_grace_6": report["ranking_stable_vs_grace_6"],
        "ranking_by_mode": report["ranking_by_mode"],
        "frozen_sensitivities": {
            mode: {
                "naive": vals["naive_sensitivity"],
                "governed": vals["governed_sensitivity"],
                "interruptive": vals["interruptive_sensitivity"],
            }
            for mode, vals in frozen.items()
        },
    }
    print(json.dumps(compact, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.json_out}")
    return 0 if report["ranking_stable_vs_grace_6"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
