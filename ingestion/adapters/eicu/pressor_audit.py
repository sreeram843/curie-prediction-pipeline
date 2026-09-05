"""Read-only pressor unit audit for eICU infusionDrug (plan B1 eICU companion).

Mirrors ``ingestion.adapters.mimic.pressor_audit``: streams
``infusiondrug.csv.gz`` once, reports the raw drugname/unit spelling
distribution for pressor rows, and classifies each row under the shared
conversion policy (known vs unknown with explicit reasons, weight
availability). Never alters source files, never changes adapter behavior.

AUDIT-ONLY output; results are not frozen study numbers.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ingestion.adapters.eicu.convert import _VASO_AGENTS, _iter_csv_gz
from ingestion.adapters.mimic.vasopressors import convert_pressor_dose, valid_weight_kg


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _pressor_agent(name: str) -> str | None:
    text = (name or "").strip().lower()
    if not text:
        return None
    for key in _VASO_AGENTS:
        if key in text:
            return "other" if key in {"phenylephrine", "vasopressin"} else key
    return None


def _rate_unit_from_drugname(name: str) -> str:
    text = (name or "").strip()
    if "(" in text and ")" in text:
        return text[text.rfind("(") + 1 : text.rfind(")")].strip()
    return ""


def audit_eicu_pressors(
    root: Path,
    *,
    limit_rows: int | None = None,
) -> dict[str, Any]:
    """Unit distribution + dose classification for eICU pressor infusion rows."""
    per_unit: dict[str, dict[str, int]] = defaultdict(Counter)
    per_agent: dict[str, int] = Counter()
    n_press = 0
    n_nonpress = 0
    seen = 0
    for row in _iter_csv_gz(root / "infusiondrug.csv.gz"):
        seen += 1
        if limit_rows is not None and seen >= limit_rows:
            break
        agent = _pressor_agent(row.get("drugname") or "")
        if agent is None:
            n_nonpress += 1
            continue
        n_press += 1
        per_agent[agent] += 1
        raw_unit = _rate_unit_from_drugname(row.get("drugname") or "")
        slot = per_unit[raw_unit or "<blank>"]
        slot["rows"] += 1
        rate = _to_float(row.get("drugrate"))
        weight = _to_float(row.get("patientweight"))
        conv = convert_pressor_dose(
            rate=rate,
            rate_uom=raw_unit or None,
            weight_kg=weight,
            weight_available=valid_weight_kg(weight),
            agent=agent,
        )
        if conv.known:
            slot["dose_known"] += 1
        else:
            slot["dose_unknown"] += 1
            slot[f"unknown:{conv.reason}"] += 1
        if rate is None or not math.isfinite(rate):
            slot["rate_missing_or_non_finite"] += 1
        if conv.reason in {
            "weight_unavailable_or_only_future",
            "invalid_or_missing_weight",
        }:
            slot["weight_needed_but_unavailable"] += 1

    return {
        "dataset": "eicu-crd",
        "table": "infusiondrug.csv.gz",
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "rows_scanned": seen,
        "mapped_pressor_rows": n_press,
        "non_pressor_rows": n_nonpress,
        "agents": dict(sorted(per_agent.items())),
        "units": {unit: dict(counts) for unit, counts in sorted(per_unit.items())},
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: run the read-only eICU pressor unit audit on an eICU root."""
    parser = argparse.ArgumentParser(
        description="Read-only eICU infusiondrug pressor unit audit"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--limit-rows", type=int, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = audit_eicu_pressors(Path(args.root), limit_rows=args.limit_rows)
    print(json.dumps(report, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
