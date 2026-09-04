"""eICU demo CSVs → demo-schema stays.

Offsets are minutes from unit admit. We synthesize a naive epoch so scoring
windows are consistent; calendar dates in the demo are incomplete (year +
time-of-day only).
"""

from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ingestion.adapters.demo_schema import downsample_hourly
from ingestion.adapters.eicu.paths import require_eicu_demo_dir
from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu.convert import _emit_stay

SCHEMA_VERSION = "1.0.0"
EPOCH = datetime(2015, 1, 1, 0, 0, 0)

_LAB_NAMES: dict[str, str] = {
    "creatinine": c.CREATININE,
    "platelets x 1000": c.PLATELETS,
    "total bilirubin": c.BILIRUBIN_TOTAL,
    "fio2": c.FIO2,
}

def _iter_csv_gz(path: Path) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield {k: (v if v is not None else "") for k, v in row.items()}


def _to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _offset_ts(offset_min: Any) -> str | None:
    minutes = _to_float(offset_min)
    if minutes is None:
        return None
    clock = EPOCH + timedelta(minutes=minutes)
    return clock.strftime("%Y-%m-%d %H:%M:%S")


def _event(
    *,
    concept: str,
    itemid: str,
    valuenum: float,
    unit: str,
    charttime: str,
) -> dict[str, Any]:
    return {
        "concept": concept,
        "itemid": itemid,
        "valuenum": valuenum,
        "unit": unit,
        "charttime": charttime,
        "storetime": charttime,
    }


def _maybe_fio2_percent(value: float) -> float:
    # eICU FiO2 is usually percent; a fraction in (0, 1] is scaled up.
    if 0 < value <= 1.0:
        return value * 100.0
    return value


def convert_eicu_rows(
    *,
    patients: Iterable[dict[str, str]],
    labs: Iterable[dict[str, str]],
    vital_periodic: Iterable[dict[str, str]],
    vital_aperiodic: Iterable[dict[str, str]],
    nurse_charting: Iterable[dict[str, str]],
    limit: int | None = None,
) -> dict[str, Any]:
    stays_meta: dict[str, dict[str, Any]] = {}
    for row in patients:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if not stay_id:
            continue
        subject_id = (
            row.get("uniquepid") or row.get("patienthealthsystemstayid") or stay_id
        ).strip()
        out_off = _to_float(row.get("unitdischargeoffset"))
        stays_meta[stay_id] = {
            "stay_id": stay_id,
            "subject_id": subject_id,
            "hadm_id": (row.get("patienthealthsystemstayid") or "").strip(),
            "intime": EPOCH.strftime("%Y-%m-%d %H:%M:%S"),
            "outtime": (EPOCH + timedelta(minutes=out_off or 0)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        if limit is not None and len(stays_meta) >= limit:
            break

    wanted = set(stays_meta)
    lab_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chart_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    def add_chart(stay_id: str, ev: dict[str, Any]) -> None:
        chart_events[stay_id].append(ev)
        counts[ev["concept"]] += 1

    def add_lab(stay_id: str, ev: dict[str, Any]) -> None:
        lab_events[stay_id].append(ev)
        counts[ev["concept"]] += 1

    for row in labs:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        name = (row.get("labname") or "").strip().lower()
        concept = _LAB_NAMES.get(name)
        if concept is None:
            continue
        val = _to_float(row.get("labresult"))
        if val is None:
            continue
        ts = _offset_ts(row.get("labresultoffset"))
        if ts is None:
            continue
        if concept == c.FIO2:
            val = _maybe_fio2_percent(val)
            add_chart(
                stay_id,
                _event(
                    concept=concept, itemid="lab-fio2", valuenum=val, unit="%", charttime=ts
                ),
            )
        else:
            unit = row.get("labmeasurenamesystem") or ""
            add_lab(
                stay_id,
                _event(
                    concept=concept, itemid=name, valuenum=val, unit=unit, charttime=ts
                ),
            )

    for row in vital_periodic:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("observationoffset"))
        if ts is None:
            continue
        sao2 = _to_float(row.get("sao2"))
        if sao2 is not None:
            add_chart(
                stay_id,
                _event(concept=c.SPO2, itemid="sao2", valuenum=sao2, unit="%", charttime=ts),
            )
        mean_bp = _to_float(row.get("systemicmean"))
        if mean_bp is not None:
            add_chart(
                stay_id,
                _event(
                    concept=c.MAP,
                    itemid="systemicmean",
                    valuenum=mean_bp,
                    unit="mmHg",
                    charttime=ts,
                ),
            )

    for row in vital_aperiodic:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("observationoffset"))
        if ts is None:
            continue
        nibp = _to_float(row.get("noninvasivemean"))
        if nibp is not None:
            add_chart(
                stay_id,
                _event(
                    concept=c.MAP,
                    itemid="nibp-mean",
                    valuenum=nibp,
                    unit="mmHg",
                    charttime=ts,
                ),
            )

    for row in nurse_charting:
        stay_id = (row.get("patientunitstayid") or "").strip()
        if stay_id not in wanted:
            continue
        ts = _offset_ts(row.get("nursingchartoffset"))
        if ts is None:
            continue
        label = (row.get("nursingchartcelltypevallabel") or "").strip()
        name = (row.get("nursingchartcelltypevalname") or "").strip()
        val = _to_float(row.get("nursingchartvalue"))
        if val is None:
            continue
        blob = f"{label} {name}".lower()
        if "gcs total" in blob or blob.strip() == "glasgow coma score gcs total":
            add_chart(
                stay_id,
                _event(
                    concept=c.GCS_TOTAL,
                    itemid="gcs-total",
                    valuenum=val,
                    unit="",
                    charttime=ts,
                ),
            )
        elif label.lower() == "o2 saturation":
            add_chart(
                stay_id,
                _event(concept=c.SPO2, itemid="o2sat", valuenum=val, unit="%", charttime=ts),
            )
        elif "map (mmhg)" in blob:
            add_chart(
                stay_id,
                _event(
                    concept=c.MAP,
                    itemid="nurse-map",
                    valuenum=val,
                    unit="mmHg",
                    charttime=ts,
                ),
            )

    stays = []
    for stay_id, meta in stays_meta.items():
        labs_ds = downsample_hourly(lab_events.get(stay_id, []))
        charts_ds = downsample_hourly(chart_events.get(stay_id, []))
        stays.append(
            _emit_stay(
                stay_meta=meta,
                lab_events=labs_ds,
                chart_events=charts_ds,
                diagnoses=[],
                evidence_prefix="eicu",
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_pin": {
            "name": "eicu-crd-demo",
            "version": "2.0.1",
            "note": (
                "Open PhysioNet eICU demo. Plumbing / coverage only; no Sepsis-3 "
                "onset labels. Vitals downsampled to one value per concept-hour."
            ),
        },
        "coverage": {"concepts": dict(counts), "stays": len(stays)},
        "stays": stays,
        "warnings": [],
    }


def convert_eicu(root: Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    root = root or require_eicu_demo_dir()
    patients = list(_iter_csv_gz(root / "patient.csv.gz"))
    if limit is not None:
        patients = patients[:limit]
    wanted = {(p.get("patientunitstayid") or "").strip() for p in patients}

    def _filter(path: Path) -> Iterator[dict[str, str]]:
        if not path.is_file():
            return
        yield from (
            row
            for row in _iter_csv_gz(path)
            if (row.get("patientunitstayid") or "").strip() in wanted
        )

    return convert_eicu_rows(
        patients=patients,
        labs=_filter(root / "lab.csv.gz"),
        vital_periodic=_filter(root / "vitalPeriodic.csv.gz"),
        vital_aperiodic=_filter(root / "vitalAperiodic.csv.gz"),
        nurse_charting=_filter(root / "nurseCharting.csv.gz"),
        limit=None,
    )
