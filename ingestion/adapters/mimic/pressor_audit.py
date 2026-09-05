"""Read-only pressor unit audit for MIMIC-IV inputevents (plan B1 step 1).

Companion to ``ingestion.adapters.mimic.vasopressors`` (which owns the conversion
policy). This module only *observes*: it streams ``icu/inputevents.csv.gz`` once,
reports the raw ``rateuom`` spelling distribution for mapped pressor rows, and
classifies each row's dose under the shared conversion policy (known vs unknown
with explicit reasons, plus weight availability). It never alters source files
and never changes how the adapter scores.

AUDIT-ONLY output; results are not frozen study numbers.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.loader import iter_csv_gz
from ingestion.adapters.mimic.vasopressors import convert_pressor_dose, valid_weight_kg


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def audit_inputevents_pressors(
    root: Path,
    *,
    pressor_map: dict[int, str] | None = None,
    limit_rows: int | None = None,
) -> dict[str, Any]:
    """Unit distribution + dose classification for mapped pressor rows."""
    agent_of = pressor_map or im.INPUT_VASOPRESSORS
    wanted = {str(i) for i in agent_of}
    per_unit: dict[str, dict[str, int]] = defaultdict(Counter)
    n_press = 0
    n_nonpress = 0
    seen = 0
    path = root / "icu" / "inputevents.csv.gz"
    for row in iter_csv_gz(path):
        seen += 1
        if limit_rows is not None and seen >= limit_rows:
            break
        if row.get("itemid") not in wanted:
            n_nonpress += 1
            continue
        n_press += 1
        raw_unit = (row.get("rateuom") or "").strip()
        slot = per_unit[raw_unit or "<blank>"]
        slot["rows"] += 1
        rate = _to_float(row.get("rate"))
        weight = _to_float(row.get("patientweight"))
        conv = convert_pressor_dose(
            rate=rate,
            rate_uom=raw_unit,
            weight_kg=weight,
            weight_available=valid_weight_kg(weight),
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
        "dataset": "mimic-iv",
        "table": "icu/inputevents.csv.gz",
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "rows_scanned": seen,
        "mapped_pressor_rows": n_press,
        "non_pressor_rows": n_nonpress,
        "units": {unit: dict(counts) for unit, counts in sorted(per_unit.items())},
        "mapped_itemids": {str(k): v for k, v in sorted(agent_of.items())},
    }
