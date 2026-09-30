#!/usr/bin/env python3
"""Run MIMIC Stage B secondary fairness scorecards (lead gate + ICD).

Replays the locked operating point on a protocol split (default: test), joins
pinned discharge sepsis ICD codes, and writes a fairness report. Does not
retune thresholds or change PE-1/PE-2.

Example::

    python scripts/run_mimic_fairness_scorecards.py \\
      --index-dir data/index/mimic-iv \\
      --labels data/stage_b/mimic_labels.v2.json \\
      --mimic-dir /path/to/mimiciv/3.1 \\
      --workers 6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from eval.mimic_study.fairness import build_fairness_report
from eval.mimic_study.icd_sepsis import (
    annotate_icd_sepsis_positive,
    load_icd_sepsis_hadm_ids,
    load_icd_sepsis_pin,
)
from eval.mimic_study.indexing import load_stays
from eval.mimic_study.protocol import load_protocol
from eval.mimic_study.stage_b_run import evaluate_stay_ids, split_stay_ids
from eval.mimic_study.study import FROZEN_DIR
from ingestion.adapters.mimic.paths import require_mimic_dir


def _load_operating_point(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    knobs = payload.get("knobs")
    if not isinstance(knobs, dict):
        raise ValueError(f"operating point missing knobs: {path}")
    return payload


def _resolve_mimic_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    return require_mimic_dir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIMIC fairness scorecards (CURIE-041 secondary)")
    parser.add_argument("--index-dir", type=Path, default=Path("data/index/mimic-iv"))
    parser.add_argument("--labels", type=Path, default=Path("data/stage_b/mimic_labels.v2.json"))
    parser.add_argument("--mimic-dir", type=Path, default=None)
    parser.add_argument("--protocol-version", choices=("v1", "v2"), default="v2")
    parser.add_argument(
        "--operating-point",
        type=Path,
        default=FROZEN_DIR / "operating_point.v2.json",
    )
    parser.add_argument("--split", choices=("development", "calibration", "test"), default="test")
    parser.add_argument("--min-lead-hours", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None, help="smoke/debug only")
    parser.add_argument(
        "--progress",
        type=Path,
        default=Path("data/stage_b/fairness_progress.json"),
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=Path("data/stage_b/fairness_scorecards.test.json"),
    )
    parser.add_argument(
        "--rows-out",
        type=Path,
        default=None,
        help="Optional path to save compact replay rows (can be large).",
    )
    args = parser.parse_args(argv)

    mimic_dir = _resolve_mimic_dir(args.mimic_dir)
    protocol = load_protocol(version=args.protocol_version)
    op = _load_operating_point(args.operating_point)
    knobs = op["knobs"]
    n_workers = args.workers if args.workers is not None else max(1, (os.cpu_count() or 2) - 2)

    by_split = split_stay_ids(
        args.index_dir, protocol=protocol, labels_path=args.labels
    )
    stay_ids = list(by_split.get(args.split) or [])
    if args.limit and args.limit > 0:
        stay_ids = stay_ids[: args.limit]
    if not stay_ids:
        print(f"ERROR: no stays for split={args.split}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "phase": "replay",
                "split": args.split,
                "n_stays": len(stay_ids),
                "candidate_id": op.get("candidate_id"),
                "workers": n_workers,
            }
        ),
        flush=True,
    )
    rows = evaluate_stay_ids(
        index_dir=args.index_dir,
        labels_path=args.labels,
        protocol_version=args.protocol_version,
        stay_ids=stay_ids,
        knobs=knobs,
        workers=n_workers,
        progress_path=args.progress,
        phase=f"fairness:{args.split}",
    )

    hadm_by_stay = {
        str(row["stay_id"]): str(row.get("hadm_id") or "")
        for row in load_stays(args.index_dir)
    }
    pin = load_icd_sepsis_pin()
    print(
        json.dumps({"phase": "icd_load", "mimic_dir": str(mimic_dir), "pin_id": pin["pin_id"]}),
        flush=True,
    )
    icd_hadms = load_icd_sepsis_hadm_ids(mimic_dir, pin=pin)
    annotated = annotate_icd_sepsis_positive(
        rows,
        icd_positive_hadm_ids=icd_hadms,
        hadm_by_stay=hadm_by_stay,
    )

    report = build_fairness_report(
        annotated,
        protocol=protocol,
        min_lead_hours=args.min_lead_hours,
        icd_pin_meta=pin,
    )
    report["run"] = {
        "split": args.split,
        "n_stays": len(annotated),
        "candidate_id": op.get("candidate_id"),
        "operating_point": str(args.operating_point),
        "mimic_dir": str(mimic_dir),
        "icd_positive_hadm_ids": len(icd_hadms),
        "min_lead_hours": args.min_lead_hours,
        "workers": n_workers,
        "limit": args.limit,
    }

    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(report, indent=2) + "\n")
    if args.rows_out is not None:
        # Drop bulky score trajectories if present.
        slim = []
        for row in annotated:
            slim.append(
                {
                    k: v
                    for k, v in row.items()
                    if k not in {"score_trajectory"}
                }
            )
        args.rows_out.parent.mkdir(parents=True, exist_ok=True)
        args.rows_out.write_text(json.dumps({"stays": slim}, indent=2) + "\n")

    primary = report["primary_reference"]["summary"]
    lead = report["lead_gated"]["summary"]
    icd = report["icd_sepsis"]
    print(
        json.dumps(
            {
                "report_out": str(args.report_out),
                "primary_governed_sensitivity": primary.get("governed_sensitivity"),
                "lead2_governed_sensitivity": lead.get("governed_sensitivity"),
                "mean_in_window_lead_hours_primary": primary.get("mean_in_window_lead_hours"),
                "icd_positive_stays": icd["cohort"]["icd_positive"],
                "icd_any_alert_governed_sensitivity": icd["any_alert_during_stay"]["governed"][
                    "sensitivity"
                ],
                "icd_overlap_window_governed_sensitivity": icd["sepsis3_window_among_overlap"][
                    "governed"
                ]["sensitivity"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
