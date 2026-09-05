#!/usr/bin/env python3
"""Build the reproducible stay-level index for MIMIC-IV / eICU source files.

Never modifies downloaded PhysioNet files — reads them once and writes a
separate, gitignored Parquet index (``data/index/<dataset>/`` by default).

Examples::

    python scripts/build_mimic_index.py --dataset mimic --limit 50
    python scripts/build_mimic_index.py --dataset mimic --limit 0            # full
    python scripts/build_mimic_index.py --dataset eicu --limit 0
    python scripts/build_mimic_index.py --dataset mimic --items all --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.mimic_study.indexing import build_index, default_index_dir


def _resolve_source(dataset: str, source: Path | None) -> Path:
    if source is not None:
        return Path(source).expanduser().resolve()
    if dataset == "mimic":
        from ingestion.adapters.mimic.paths import mimic_dir

        return mimic_dir()
    from ingestion.adapters.eicu.paths import eicu_dir

    return eicu_dir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the MIMIC/eICU stay index")
    parser.add_argument("--dataset", choices=("mimic", "eicu"), default="mimic")
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="source root (default: CURIE_MIMIC_DIR / CURIE_EICU_DIR)",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=None,
        help="index output dir (default: data/index/<dataset>)",
    )
    parser.add_argument("--limit", type=int, default=0, help="max stays (0 = all)")
    parser.add_argument("--items", choices=("mapped", "all"), default="mapped")
    parser.add_argument("--dataset-version", default=None)
    parser.add_argument("--extract-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="overwrite an existing index")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        source_root = _resolve_source(args.dataset, args.source)
        index_dir = args.index_dir or default_index_dir(args.dataset)
        meta = build_index(
            source_root=source_root,
            index_dir=index_dir,
            dataset=args.dataset,
            limit=args.limit,
            items=args.items,
            dataset_version=args.dataset_version,
            extract_date=args.extract_date,
            force=args.force,
        )
    except Exception as exc:  # noqa: BLE001 — CLI must fail closed with context
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = {
        "index_dir": str(index_dir),
        "dataset": meta["dataset"],
        "stays": meta["stays"],
        "events": meta["events"],
        "index_hash": meta["index_hash"],
        "timestamp_failures": {
            src: info.get("timestamp_failures")
            for src, info in meta["source_files"].items()
            if info.get("timestamp_failures")
        },
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(meta, indent=2) + "\n")
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
