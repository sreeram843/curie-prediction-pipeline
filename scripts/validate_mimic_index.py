#!/usr/bin/env python3
"""Validate the MIMIC/eICU stay index and reconcile it against the source files.

Checks: index hash recomputation (deterministic rerun proof), stay-partition
coverage, per-stay row counts, timestamp ordering, unit distributions, and
timestamp-parse failure counts. With ``--source`` (or when the build-time
source root still exists), it also re-scans source files for a bounded sample
of stays and proves row-level source/index equality, including source hashes.

Exit code 0 when all checks pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.mimic_study.indexing import (
    default_index_dir,
    load_index_meta,
    reconcile_source_to_index,
    validate_index,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate + reconcile the stay index")
    parser.add_argument("--dataset", choices=("mimic", "eicu"), default="mimic")
    parser.add_argument("--index-dir", type=Path, default=None)
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="source root for reconciliation (default: meta.source_root if present)",
    )
    parser.add_argument("--stay-ids", nargs="*", default=None)
    parser.add_argument("--reconcile-limit", type=int, default=25, help="stays (0 = all)")
    parser.add_argument("--skip-reconcile", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    index_dir = args.index_dir or default_index_dir(args.dataset)
    try:
        report = validate_index(index_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    reconcile = None
    if not args.skip_reconcile:
        try:
            meta = load_index_meta(index_dir)
            source_root = args.source or Path(meta.get("source_root") or "")
            if source_root.is_dir():
                reconcile = reconcile_source_to_index(
                    source_root=source_root,
                    index_dir=index_dir,
                    dataset=meta["config"]["dataset"],
                    stay_ids=args.stay_ids,
                    limit=args.reconcile_limit,
                )
                report["reconciliation"] = reconcile
            else:
                print(
                    f"note: source root {source_root} unavailable; skipping reconciliation",
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001
            report["reconciliation"] = {"ok": False, "error": str(exc)}

    print(json.dumps(report, indent=2, default=str))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, default=str) + "\n")

    ok = report.get("ok", False)
    if reconcile is not None:
        ok = ok and reconcile.get("ok", False)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
