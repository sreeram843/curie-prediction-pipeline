"""MIMIC-IV FHIR demo NDJSON → demo-schema stays."""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ingestion.adapters.demo_schema import downsample_hourly, naive_iso
from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.timeline import parse_mimic_ts
from ingestion.adapters.mimic_fhir.paths import require_mimic_fhir_demo_dir
from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu.convert import _emit_stay

SCHEMA_VERSION = "1.0.0"

_LAB_ITEMIDS: dict[str, str] = {
    str(i): c.CREATININE for i in im.LAB_CREATININE
} | {
    str(i): c.PLATELETS for i in im.LAB_PLATELETS
} | {
    str(i): c.BILIRUBIN_TOTAL for i in im.LAB_BILIRUBIN_TOTAL
}

_CHART_ITEMIDS: dict[str, str] = {
    str(i): c.MAP for i in im.CHART_MAP | {220181}
} | {
    str(i): c.SPO2 for i in im.CHART_SPO2
} | {
    str(i): c.FIO2 for i in im.CHART_FIO2
} | {
    str(i): c.GCS_EYE for i in im.CHART_GCS_EYE
} | {
    str(i): c.GCS_VERBAL for i in im.CHART_GCS_VERBAL
} | {
    str(i): c.GCS_MOTOR for i in im.CHART_GCS_MOTOR
} | {
    str(i): c.CREATININE for i in im.CHART_CREATININE
} | {
    str(i): c.BILIRUBIN_TOTAL for i in im.CHART_BILIRUBIN
} | {
    str(i): c.PLATELETS for i in im.CHART_PLATELETS
}


def _iter_ndjson_gz(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _ref_id(ref: Any) -> str | None:
    if not isinstance(ref, dict):
        return None
    raw = ref.get("reference") or ""
    if "/" in raw:
        return raw.split("/", 1)[1]
    return raw or None


def _coding_code(resource: dict[str, Any]) -> str | None:
    coding = ((resource.get("code") or {}).get("coding") or [])
    if not coding:
        return None
    return str(coding[0].get("code") or "").strip() or None


def _quantity(resource: dict[str, Any]) -> tuple[float | None, str]:
    qty = resource.get("valueQuantity") or {}
    raw = qty.get("value")
    try:
        val = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        val = None
    return val, str(qty.get("unit") or qty.get("code") or "")


def _event_times(resource: dict[str, Any]) -> tuple[str | None, str | None]:
    chart = naive_iso(resource.get("effectiveDateTime"))
    store = naive_iso(resource.get("issued")) or chart
    return chart, store


def convert_fhir_resources(
    *,
    encounters: Iterable[dict[str, Any]],
    labs: Iterable[dict[str, Any]],
    charts: Iterable[dict[str, Any]],
    limit: int | None = None,
) -> dict[str, Any]:
    stays_meta: dict[str, dict[str, Any]] = {}
    patient_stays: dict[str, list[str]] = defaultdict(list)
    stay_windows: dict[str, tuple[Any, Any]] = {}

    for enc in encounters:
        stay_id = str(enc.get("id") or "").strip()
        if not stay_id:
            continue
        subject = _ref_id(enc.get("subject")) or stay_id
        period = enc.get("period") or {}
        start = naive_iso(period.get("start"))
        end = naive_iso(period.get("end"))
        ident = ""
        for ident_row in enc.get("identifier") or []:
            if "encounter-icu" in str(ident_row.get("system") or ""):
                ident = str(ident_row.get("value") or "")
                break
        stays_meta[stay_id] = {
            "stay_id": stay_id,
            "subject_id": subject,
            "hadm_id": ident,
            "intime": start,
            "outtime": end,
        }
        start_dt = parse_mimic_ts(start)
        end_dt = parse_mimic_ts(end)
        stay_windows[stay_id] = (start_dt, end_dt)
        patient_stays[subject].append(stay_id)
        if limit is not None and len(stays_meta) >= limit:
            break

    wanted = set(stays_meta)
    lab_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chart_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    def _in_window(stay_id: str, charttime: str | None) -> bool:
        clock = parse_mimic_ts(charttime)
        start_dt, end_dt = stay_windows.get(stay_id, (None, None))
        if clock is None or start_dt is None:
            return False
        if clock < start_dt:
            return False
        if end_dt is not None and clock > end_dt:
            return False
        return True

    for res in labs:
        code = _coding_code(res)
        concept = _LAB_ITEMIDS.get(code or "")
        if concept is None:
            continue
        val, unit = _quantity(res)
        if val is None:
            continue
        chart, store = _event_times(res)
        if chart is None:
            continue
        subject = _ref_id(res.get("subject"))
        for stay_id in patient_stays.get(subject or "", []):
            if stay_id not in wanted or not _in_window(stay_id, chart):
                continue
            lab_events[stay_id].append(
                {
                    "concept": concept,
                    "itemid": code,
                    "valuenum": val,
                    "unit": unit,
                    "charttime": chart,
                    "storetime": store,
                }
            )
            counts[concept] += 1

    for res in charts:
        stay_id = _ref_id(res.get("encounter"))
        if stay_id not in wanted:
            continue
        code = _coding_code(res)
        concept = _CHART_ITEMIDS.get(code or "")
        if concept is None:
            continue
        val, unit = _quantity(res)
        if val is None:
            continue
        chart, store = _event_times(res)
        if chart is None:
            continue
        chart_events[stay_id].append(
            {
                "concept": concept,
                "itemid": code,
                "valuenum": val,
                "unit": unit,
                "charttime": chart,
                "storetime": store,
            }
        )
        counts[concept] += 1

    stays = []
    for stay_id, meta in stays_meta.items():
        stays.append(
            _emit_stay(
                stay_meta=meta,
                lab_events=downsample_hourly(lab_events.get(stay_id, [])),
                chart_events=downsample_hourly(chart_events.get(stay_id, [])),
                diagnoses=[],
                evidence_prefix="fhir",
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_pin": {
            "name": "mimic-iv-fhir-demo",
            "version": "2.1.0",
            "note": (
                "Open PhysioNet MIMIC-IV demo on FHIR. Same patients as the CSV "
                "demo; plumbing only. Charts/labs downsampled to one value per "
                "concept-hour."
            ),
        },
        "coverage": {"concepts": dict(counts), "stays": len(stays)},
        "stays": stays,
        "warnings": [],
    }


def convert_mimic_fhir(root: Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    root = root or require_mimic_fhir_demo_dir()
    fhir = root / "fhir"
    return convert_fhir_resources(
        encounters=_iter_ndjson_gz(fhir / "MimicEncounterICU.ndjson.gz"),
        labs=_iter_ndjson_gz(fhir / "MimicObservationLabevents.ndjson.gz"),
        charts=_iter_ndjson_gz(fhir / "MimicObservationChartevents.ndjson.gz"),
        limit=limit,
    )
