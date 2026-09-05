"""Read-only eICU-CRD pressor unit audit (CURIE-051 / plan B1 task 5).

Streams infusionDrug.csv.gz and reports, for pressor drugnames: the unit
distribution embedded in drugname parens, drugrate missingness/invalidity,
patientweight availability per unit, and which unit spellings the current
parser would (not) convert. Aggregate counts only; modifies nothing.

Point it at the credentialed eICU-CRD v2.0 root via CURIE_EICU_DIR
(same resolution as the adapter) or --root.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ingestion.adapters.eicu.paths import eicu_dir, require_eicu_dir

PRESSOR_KEYS = (
    "norepinephrine",
    "epinephrine",
    "dopamine",
    "dobutamine",
    "phenylephrine",
    "vasopressin",
)


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw == "" or str(raw).lower() in {"none", "nan", "inf", "-inf"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _agent(name: str) -> str | None:
    low = name.lower()
    for key in PRESSOR_KEYS:
        if key in low:
            return "other" if key in {"phenylephrine", "vasopressin"} else key
    return None


def _unit(name: str) -> str:
    if "(" in name and ")" in name:
        return " ".join(name[name.rfind("(") + 1 : name.rfind(")")].strip().lower().split())
    return "<missing>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    root = Path(args.root) if args.root else (eicu_dir() if _configured() else require_eicu_dir())
    path = root / "infusionDrug.csv.gz"

    unit_rows: dict[str, Counter] = defaultdict(Counter)
    agent_rows: Counter = Counter()
    per_unit_parser_verdict: dict[str, Counter] = defaultdict(Counter)
    scanned = 0
    pressor = 0
    print(f"scanning {path} ...", file=sys.stderr)
    with gzip.open(path, "rt") as fh:
        for row in csv.DictReader(fh):
            if args.limit is not None and scanned >= args.limit:
                break
            scanned += 1
            name = (row.get("drugname") or "").strip()
            agent = _agent(name)
            if agent is None:
                continue
            pressor += 1
            agent_rows[agent] += 1
            unit = _unit(name)
            unit_rows[agent][unit] += 1
            rate = _to_float(row.get("drugrate"))
            weight = _to_float(row.get("patientweight"))
            slot = unit_rows[agent]
            if rate is None:
                slot["rate_missing"] += 1
            elif not math.isfinite(rate):
                slot["rate_non_finite"] += 1
            elif rate <= 0:
                slot["rate_non_positive"] += 1
            if unit == "mcg/min":
                if weight is None or not (math.isfinite(weight) and 1.0 <= weight <= 500.0):
                    slot["weight_missing_or_invalid"] += 1
            # What the current converter would do with this row (B1 audit):
            if rate is None or rate <= 0 or not math.isfinite(rate):
                verdict = "unknown:rate"
            elif unit == "mcg/kg/min" or "mcg/kg/minute" in unit:
                verdict = "known:passthrough"
            elif unit == "mcg/min":
                verdict = (
                    "known:divide_by_weight"
                    if weight and weight > 0
                    else "unknown:weight"
                )
            elif "mg" in unit:
                verdict = "unknown:mg_unit_not_converted"
            else:
                verdict = "unknown:unit"
            per_unit_parser_verdict[unit][verdict] += 1

    report: dict[str, Any] = {
        "audit_id": "eicu-pressor-units.v1",
        "dataset": "eICU-CRD v2.0",
        "table": "infusionDrug.csv.gz",
        "rows_scanned": scanned,
        "pressor_rows": pressor,
        "agents": dict(agent_rows),
        "units_by_agent": {a: dict(c) for a, c in sorted(unit_rows.items())},
        "current_parser_verdicts": {
            unit: dict(counts) for unit, counts in sorted(per_unit_parser_verdict.items())
        },
    }
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


def _configured() -> bool:
    import os

    return bool(os.environ.get("CURIE_EICU_DIR") or os.environ.get("EICU_DIR"))


if __name__ == "__main__":
    raise SystemExit(main())
