"""CSV.gz helpers for MIMIC-IV demo tables."""

from __future__ import annotations

import csv
import gzip
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def iter_csv_gz(path: Path) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {k: (v if v is not None else "") for k, v in row.items()}


def load_icustays(root: Path, *, limit: int | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in iter_csv_gz(root / "icu" / "icustays.csv.gz"):
        rows.append(row)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw == "" or raw.lower() in {"none", "nan"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def index_labevents(
    root: Path,
    *,
    subject_ids: set[str],
    itemids: set[int],
) -> dict[str, list[dict[str, Any]]]:
    """subject_id → list of {hadm_id, charttime, itemid, valuenum}."""
    wanted = {str(i) for i in itemids}
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in subject_ids}
    path = root / "hosp" / "labevents.csv.gz"
    for row in iter_csv_gz(path):
        sid = row.get("subject_id") or ""
        if sid not in subject_ids:
            continue
        if row.get("itemid") not in wanted:
            continue
        val = _to_float(row.get("valuenum"))
        if val is None:
            continue
        out[sid].append(
            {
                "hadm_id": row.get("hadm_id") or "",
                "charttime": row.get("charttime") or "",
                "itemid": int(row["itemid"]),
                "valuenum": val,
            }
        )
    return out


def index_chartevents(
    root: Path,
    *,
    stay_ids: set[str],
    itemids: set[int],
) -> dict[str, list[dict[str, Any]]]:
    wanted = {str(i) for i in itemids}
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in stay_ids}
    path = root / "icu" / "chartevents.csv.gz"
    for row in iter_csv_gz(path):
        stay = row.get("stay_id") or ""
        if stay not in stay_ids:
            continue
        if row.get("itemid") not in wanted:
            continue
        val = _to_float(row.get("valuenum"))
        if val is None:
            continue
        out[stay].append(
            {
                "charttime": row.get("charttime") or "",
                "itemid": int(row["itemid"]),
                "valuenum": val,
            }
        )
    return out


def index_inputevents_pressors(
    root: Path,
    *,
    stay_ids: set[str],
    itemids: set[int],
) -> dict[str, list[dict[str, Any]]]:
    wanted = {str(i) for i in itemids}
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in stay_ids}
    path = root / "icu" / "inputevents.csv.gz"
    for row in iter_csv_gz(path):
        stay = row.get("stay_id") or ""
        if stay not in stay_ids:
            continue
        if row.get("itemid") not in wanted:
            continue
        out[stay].append(
            {
                "starttime": row.get("starttime") or "",
                "endtime": row.get("endtime") or "",
                "itemid": int(row["itemid"]),
                "rate": _to_float(row.get("rate")),
                "rateuom": row.get("rateuom") or "",
            }
        )
    return out


def index_outputevents_urine(
    root: Path,
    *,
    stay_ids: set[str],
    itemids: set[int],
) -> dict[str, list[dict[str, Any]]]:
    wanted = {str(i) for i in itemids}
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in stay_ids}
    path = root / "icu" / "outputevents.csv.gz"
    for row in iter_csv_gz(path):
        stay = row.get("stay_id") or ""
        if stay not in stay_ids:
            continue
        if row.get("itemid") not in wanted:
            continue
        val = _to_float(row.get("value"))
        if val is None:
            continue
        out[stay].append(
            {
                "charttime": row.get("charttime") or "",
                "itemid": int(row["itemid"]),
                "value": val,
            }
        )
    return out
