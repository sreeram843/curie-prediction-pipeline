"""Read-only MIMIC-IV vasopressor unit audit (CURIE-051 / plan B1).

Streams icu/inputevents.csv.gz and icu/chartevents.csv.gz and reports, for
mapped pressor itemids: rateuom distribution, rate/unit missingness,
invalid-rate counts, order-category and status distribution, endtime
missingness, and weight availability (latest charted weight at or before each
pressor starttime).

Aggregate counts only. Does not modify any file. Point it at the credentialed
MIMIC-IV 3.1 root via CURIE_MIMIC_DIR (same resolution as the adapter).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ingestion.adapters.mimic.paths import require_mimic_dir

# Current mapped agents (ingestion/adapters/mimic/item_map.py) plus every
# pressor-ish itemid observed in d_items (audit superset; mapping gaps are
# reported, not silently scored).
MAPPED_ITEMIDS: dict[int, str] = {
    221906: "norepinephrine",
    221289: "epinephrine",
    229617: "epinephrine",
    221662: "dopamine",
    221653: "dobutamine",
}
AUDIT_EXTRA_ITEMIDS: dict[int, str] = {
    221749: "phenylephrine",
    229630: "phenylephrine",
    229631: "phenylephrine",
    229632: "phenylephrine",
    229789: "phenylephrine",
    222315: "vasopressin",
    221986: "milrinone",
    229709: "angiotensin_ii",
    229764: "angiotensin_ii",
}
WEIGHT_ITEMIDS: dict[int, str] = {
    224639: "daily_weight_kg",
    226512: "admission_weight_kg",
    226531: "admission_weight_lbs",
}
LBS_PER_KG = 0.45359237


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw == "" or str(raw).lower() in {"none", "nan", "inf", "-inf"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _norm_unit(raw: str | None) -> str:
    if not raw:
        return "<missing>"
    return " ".join(str(raw).strip().lower().replace("_", " ").split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap rows scanned (dry run)")
    ap.add_argument("--out", type=str, default=None, help="write JSON report here")
    args = ap.parse_args()

    root = require_mimic_dir()
    items_path = root / "icu" / "d_items.csv.gz"
    input_path = root / "icu" / "inputevents.csv.gz"
    chart_path = root / "icu" / "chartevents.csv.gz"

    labels: dict[str, str] = {}
    with gzip.open(items_path, "rt") as fh:
        for row in csv.DictReader(fh):
            labels[row["itemid"]] = row.get("label") or ""

    all_itemids = dict(MAPPED_ITEMIDS)
    all_itemids.update(AUDIT_EXTRA_ITEMIDS)
    wanted = {str(i) for i in all_itemids}

    per_item: dict[int, Counter] = defaultdict(Counter)
    rateuom_counts: Counter = Counter()
    pressor_rows: list[dict[str, Any]] = []
    order_categories: Counter = Counter()
    statuses: Counter = Counter()
    scanned = 0
    print(f"scanning {input_path} ...", file=sys.stderr)
    with gzip.open(input_path, "rt") as fh:
        for row in csv.DictReader(fh):
            if args.limit is not None and scanned >= args.limit:
                break
            scanned += 1
            if row.get("itemid") not in wanted:
                continue
            itemid = int(row["itemid"])
            per_item[itemid]["rows"] += 1
            rate_raw = row.get("rate") or ""
            rateuom_raw = row.get("rateuom") or ""
            order_categories[row.get("ordercategoryname") or "<missing>"] += 1
            statuses[row.get("statusdescription") or "<missing>"] += 1
            if not rate_raw:
                per_item[itemid]["rate_missing"] += 1
            else:
                rate = _to_float(rate_raw)
                if rate is None:
                    per_item[itemid]["rate_non_numeric"] += 1
                else:
                    if not math.isfinite(rate):
                        per_item[itemid]["rate_non_finite"] += 1
                    elif rate < 0:
                        per_item[itemid]["rate_negative"] += 1
                    elif rate == 0:
                        per_item[itemid]["rate_zero"] += 1
            if not rateuom_raw:
                per_item[itemid]["rateuom_missing"] += 1
            if not (row.get("endtime") or ""):
                per_item[itemid]["endtime_missing"] += 1
            rateuom_counts[_norm_unit(rateuom_raw)] += 1
            pressor_rows.append(
                {
                    "stay_id": row.get("stay_id") or "",
                    "itemid": itemid,
                    "starttime": row.get("starttime") or "",
                    "rate_raw": rate_raw,
                    "rateuom": _norm_unit(rateuom_raw),
                    "endtime": row.get("endtime") or "",
                }
            )

    pressor_stays = {r["stay_id"] for r in pressor_rows}
    weights: dict[str, list[tuple[datetime, int, float]]] = defaultdict(list)
    scanned_chart = 0
    print(f"pressor rows={len(pressor_rows)} stays={len(pressor_stays)}; "
          f"scanning {chart_path} for weights ...", file=sys.stderr)
    with gzip.open(chart_path, "rt") as fh:
        for row in csv.DictReader(fh):
            if args.limit is not None and scanned_chart >= args.limit:
                break
            scanned_chart += 1
            stay = row.get("stay_id") or ""
            if stay not in pressor_stays:
                continue
            if row.get("itemid") not in {str(i) for i in WEIGHT_ITEMIDS}:
                continue
            t = _parse_ts(row.get("charttime"))
            v = _to_float(row.get("valuenum"))
            if t is None or v is None:
                continue
            itemid = int(row["itemid"])
            if itemid == 226531:
                v = v * LBS_PER_KG
            weights[stay].append((t, itemid, v))

    # Weight availability per pressor row (latest weight at or before starttime).
    avail: Counter = Counter()
    age_buckets: Counter = Counter()
    rows_with_prior_weight = 0
    future_only = 0
    for r in pressor_rows:
        start = _parse_ts(r["starttime"])
        if start is None:
            avail["starttime_unparseable"] += 1
            continue
        prior = [(t, it, v) for (t, it, v) in weights.get(r["stay_id"], []) if t <= start]
        if not prior:
            later = [t for (t, _, _) in weights.get(r["stay_id"], []) if t > start]
            avail["no_weight_at_or_before"] += 1
            if later:
                future_only += 1
            continue
        rows_with_prior_weight += 1
        prior.sort(key=lambda x: x[0])
        best = prior[-1]
        hours = (start - best[0]).total_seconds() / 3600.0
        if hours <= 1:
            age_buckets["<=1h"] += 1
        elif hours <= 6:
            age_buckets["1-6h"] += 1
        elif hours <= 24:
            age_buckets["6-24h"] += 1
        else:
            age_buckets[">24h"] += 1
        avail["weight_at_or_before"] += 1

    report: dict[str, Any] = {
        "audit_id": "mimic-pressor-units.v1",
        "dataset": "MIMIC-IV 3.1",
        "inputevents_rows_scanned": scanned,
        "chartevents_rows_scanned": scanned_chart,
        "pressor_rows": len(pressor_rows),
        "pressor_stays": len(pressor_stays),
        "itemids": {
            str(i): {
                "label": labels.get(str(i), ""),
                "mapped_agent": all_itemids.get(i),
                "counts": dict(per_item[i]),
            }
            for i in all_itemids
        },
        "rateuom_distribution": dict(rateuom_counts),
        "ordercategoryname": dict(order_categories),
        "statusdescription": dict(statuses),
        "weight_availability": {
            "rows": len(pressor_rows),
            "rows_with_weight_at_or_before": rows_with_prior_weight,
            "rows_without": len(pressor_rows) - rows_with_prior_weight,
            "future_only_weight": future_only,
            "age_buckets": dict(age_buckets),
        },
    }
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
