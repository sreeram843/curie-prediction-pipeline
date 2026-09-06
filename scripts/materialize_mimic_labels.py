#!/usr/bin/env python3
"""Materialize pinned MIMIC label SQL exports into a hashed JSON artifact.

The SQL queries are intentionally an operator step. Supply their CSV/JSON
exports plus the pin produced by ``pin_mimic_code_labels.py``; this command does
not connect to PostgreSQL or download data.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from eval.mimic_study.labels.materialize import build_label_artifact, write_label_artifact


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text())
        if isinstance(value, dict):
            value = value.get("rows")
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ValueError(f"{path} must contain a JSON list of objects or {{'rows': [...]}}")
        return [dict(row) for row in value]
    with path.open(newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize pinned MIMIC label exports")
    parser.add_argument("--sepsis3", type=Path, required=True, help="Sepsis-3 export CSV/JSON")
    parser.add_argument("--kdigo", type=Path, required=True, help="KDIGO export CSV/JSON")
    parser.add_argument("--cohort", type=Path, required=True, help="Cohort CSV/JSON with stay_id")
    parser.add_argument("--source-pin", type=Path, required=True)
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--extract-date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cohort_rows = _read_rows(args.cohort)
        cohort_ids = [str(row.get("stay_id") or row.get("icustay_id") or "") for row in cohort_rows]
        source_pin = json.loads(args.source_pin.read_text())
        artifact = build_label_artifact(
            cohort_stay_ids=cohort_ids,
            sepsis_rows=_read_rows(args.sepsis3),
            kdigo_rows=_read_rows(args.kdigo),
            protocol_id=args.protocol_id,
            dataset_pin={
                "name": "mimic-iv",
                "version": args.dataset_version,
                "extract_date": args.extract_date,
            },
            source_pin=source_pin,
        )
        out = write_label_artifact(artifact, args.out)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {out} ({len(artifact['stays'])} stays)")
    print(f"content_hash={artifact['content_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
