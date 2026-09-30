#!/usr/bin/env python3
"""Run the full-cohort MIMIC-IV Stage B study (CURIE-041).

Streams stays from the Parquet index + materialized labels. Does not build a
multi-GB canonical-rows JSON.

Example::

    python scripts/run_curie_041_stage_b.py \\
      --index-dir data/index/mimic-iv \\
      --labels data/stage_b/mimic_labels.v2.json \\
      --workers 8 \\
      --write-frozen
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.mimic_study.stage_b_run import run_full_cohort_stage_b


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CURIE-041 full-cohort Stage B runner")
    parser.add_argument("--index-dir", type=Path, default=Path("data/index/mimic-iv"))
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--protocol-version", choices=("v1", "v2"), default="v2")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--limit-per-split", type=int, default=None, help="smoke/debug only")
    parser.add_argument(
        "--progress",
        type=Path,
        default=Path("data/stage_b/curie041_progress.json"),
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=Path("data/stage_b/study_report.full_cohort.json"),
    )
    parser.add_argument(
        "--miss-out",
        type=Path,
        default=Path("data/stage_b/miss_analysis.full_cohort.json"),
    )
    parser.add_argument("--frozen-dir", type=Path, default=None)
    parser.add_argument("--write-frozen", action="store_true")
    parser.add_argument("--no-write-frozen", action="store_true")
    args = parser.parse_args(argv)

    write_frozen = args.write_frozen and not args.no_write_frozen
    try:
        result = run_full_cohort_stage_b(
            index_dir=args.index_dir,
            labels_path=args.labels,
            protocol_version=args.protocol_version,
            workers=args.workers,
            progress_path=args.progress,
            report_out=args.report_out,
            miss_out=args.miss_out,
            frozen_dir=args.frozen_dir,
            write_frozen=write_frozen,
            limit_per_split=args.limit_per_split,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report = result["report"]
    print(
        json.dumps(
            {
                "protocol_id": report["protocol_id"],
                "candidate_id": report["operating_point"]["candidate_id"],
                "cohort": report.get("cohort"),
                "test_meets_pe1": report["primary_test"].get("meets_pe1"),
                "test_meets_pe2": report["primary_test"].get("meets_pe2"),
                "governed_sensitivity": report["primary_test"].get("governed_sensitivity"),
                "interruptive_reduction_ratio": report["primary_test"].get(
                    "interruptive_reduction_ratio"
                ),
                "bootstrap_ci": report.get("bootstrap_ci"),
                "miss_rate": (report.get("miss_analysis") or {}).get("miss_rate"),
                "selection_used_test": report["selection_guard"]["test_used_for_selection"],
                "content_hash": report["content_hash"],
                "manifest_hash": result["manifest"]["content_hash"],
                "wrote_frozen": write_frozen,
                "report_out": str(args.report_out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
