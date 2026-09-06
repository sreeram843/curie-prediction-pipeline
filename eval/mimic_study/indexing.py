"""Reproducible stay-level Parquet index for credentialed MIMIC-IV / eICU sources.

Phase C (paper-readiness infrastructure): build a local, gitignored, stay-partitioned
representation so bounded and full study runs do not repeatedly scan compressed source
files. The index is a **row mirror** of the source tables — one index row per selected
source row, preserving:

- ``stay_id`` (and subject/hadm identity),
- event time and availability (store) time,
- source table + row ordinal (source row identity),
- item ID and unit fields,
- raw value and normalized numeric value,
- evidence/provenance metadata (including the full source row as canonical JSON).

Clinical semantics (concept mapping, scoring, aggregation) deliberately live in the
adapters / replay harness (Phase B owns those). This module only moves rows.

Layout (gitignored, under ``data/index/<dataset>/`` by default)::

    meta.json                            # config, source hashes, counts, index hash
    stays.parquet                        # stay metadata + per-stay event counts
    events/stay_id=<id>/part-0.parquet   # stay-level partition (predicate pushdown)

PyArrow is an optional study dependency (``pip install -e ".[study]"``); the core
runtime never imports it.

Builds are deterministic: same source files + same config → same ``index_hash``.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ingestion.adapters.mimic.timeline import parse_mimic_ts

try:  # optional study dependency; core runtime never imports pyarrow eagerly
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - exercised only without the [study] extra
    pa = None  # type: ignore[assignment]
    pq = None  # type: ignore[assignment]

INDEX_SCHEMA_VERSION = "1.0.0"
BUILDER_VERSION = "0.2.0"

EICU_EPOCH = datetime(2015, 1, 1, 0, 0, 0)
_MAX_OPEN_SHARDS = 512
_TOP_UNITS = 20

EVENT_SCHEMA_KEYS = (
    "stay_id",
    "subject_id",
    "hadm_id",
    "event_family",
    "event_time",
    "availability_time",
    "source_table",
    "source_row",
    "itemid",
    "itemid_num",
    "unit",
    "value_raw",
    "value_num",
    "status",
    "is_discharge_diagnosis",
    "evidence_id",
    "extra_json",
)


class IndexError(ValueError):
    """Index build / validation / reconciliation failure."""


def _require_arrow() -> None:
    if pa is None or pq is None:
        raise IndexError(
            "pyarrow is required for the study index. Install with: pip install -e '.[study]'"
        )


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256_hex(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of the file bytes (streamed), matching ``sha256sum`` of the source."""
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _fmt_num(value: float | None) -> str:
    if value is None:
        return ""
    return format(float(value), ".17g")


def _fmt_ts(value: Any) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _hash_event_line(stay_id: str, event: dict[str, Any]) -> bytes:
    """Canonical bytes of one event row (fixed field order, no absolute paths)."""
    extra = event.get("extra_json")
    if isinstance(extra, (dict, list)):
        extra_text = json.dumps(extra, sort_keys=True, separators=(",", ":"))
    else:
        extra_text = str(extra or "")
    parts = [
        stay_id,
        str(event["event_family"]),
        str(event["source_table"]),
        str(event["source_row"]),
        _fmt_ts(event["event_time"]),
        _fmt_ts(event["availability_time"]),
        str(event["itemid"]),
        str(event["unit"]),
        str(event["value_raw"] or ""),
        _fmt_num(event["value_num"]),
        str(event["status"]),
        "1" if event["is_discharge_diagnosis"] else "0",
        extra_text,
    ]
    return "|".join(parts).encode("utf-8")


def _hash_stay_line(stay: dict[str, Any]) -> bytes:
    parts = [
        str(stay["stay_id"]),
        str(stay["subject_id"]),
        str(stay.get("hadm_id") or ""),
        _fmt_ts(stay.get("intime")),
        _fmt_ts(stay.get("outtime")),
        _fmt_ts(stay.get("dischtime")),
        str(stay.get("event_count") or 0),
        str(stay.get("extra_json") or ""),
    ]
    return "|".join(parts).encode("utf-8")


def _code_revision() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    commit = "unknown"
    branch = "unknown"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
            cwd=repo_root,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True,
            check=True, cwd=repo_root,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pass
    return {
        "git_commit": commit,
        "git_branch": branch,
        "builder_module_sha256": sha256_hex(Path(__file__).read_bytes()),
    }


def _iter_csv_gz_rows(path: Path) -> Iterator[dict[str, str]]:
    """Stream rows; wrap stream corruption in a clear, fail-closed IndexError."""
    import zlib

    try:
        with gzip.open(path, "rt", newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield {k: (v if v is not None else "") for k, v in row.items()}
    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        csv.Error,
        UnicodeDecodeError,
        zlib.error,
    ) as exc:
        raise IndexError(f"failed reading source file {path}: {exc}") from exc


def _to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if text.lower() in {"none", "nan", "inf", "-inf", "+inf"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _coerce_itemid(raw: Any) -> tuple[str, int | None]:
    if raw is None:
        return "", None
    text = str(raw).strip()
    if not text:
        return "", None
    if text.isdigit():
        return text, int(text)
    return text, None


def _eicu_offset_ts(raw: Any) -> datetime | None:
    minutes = _to_float(raw)
    if minutes is None:
        return None
    return EICU_EPOCH + timedelta(minutes=minutes)


# --------------------------------------------------------------------------- #
# Dataset specs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FamilySpec:
    family: str
    source_file: str  # relative to dataset root
    scope: str  # "stay" | "subject" | "hadm"
    scope_key: str  # row column (for subject scope the sid/hadm columns are fixed)
    time_key: str
    availability_key: str | None
    itemid_key: str
    unit_key: str
    value_raw_key: str
    value_num_key: str
    mapped_filter: Callable[[dict[str, str]], bool] | None
    is_discharge_diagnosis: bool = False


def _mimic_mapped_filters() -> dict[str, Callable[[dict[str, str]], bool]]:
    from ingestion.adapters.mimic import item_map as im
    from ingestion.adapters.mimic.vasopressors import WEIGHT_ITEMIDS

    lab_ids = {
        str(i) for i in im.LAB_CREATININE | im.LAB_PLATELETS | im.LAB_BILIRUBIN_TOTAL | im.LAB_PAO2
    }
    chart_ids = {
        str(i)
        for i in (
            im.CHART_MAP
            | im.CHART_SPO2
            | im.CHART_FIO2
            | im.CHART_GCS_EYE
            | im.CHART_GCS_VERBAL
            | im.CHART_GCS_MOTOR
            | im.CHART_CREATININE
            | im.CHART_BILIRUBIN
            | im.CHART_PLATELETS
            | set(WEIGHT_ITEMIDS)
        )
    }
    input_ids = {str(i) for i in im.INPUT_VASOPRESSORS}
    output_ids = {str(i) for i in im.OUTPUT_URINE}
    return {
        "lab": lambda row, ids=lab_ids: (row.get("itemid") or "") in ids,
        "chart": lambda row, ids=chart_ids: (row.get("itemid") or "") in ids,
        "input": lambda row, ids=input_ids: (row.get("itemid") or "") in ids,
        "output": lambda row, ids=output_ids: (row.get("itemid") or "") in ids,
        "diagnosis": lambda row: True,
    }


def _eicu_mapped_filters() -> dict[str, Callable[[dict[str, str]], bool]]:
    from ingestion.adapters.eicu.convert import (
        _LAB_NAMES,
        _RESP_FIO2_LABELS,
        _VASO_AGENTS,
    )

    lab_names = set(_LAB_NAMES)

    def _nurse(row: dict[str, str]) -> bool:
        label = (row.get("nursingchartcelltypevallabel") or "").lower()
        name = (row.get("nursingchartcelltypevalname") or "").lower()
        blob = f"{label} {name}"
        return (
            "gcs" in blob
            or "glasgow" in blob
            or label == "o2 saturation"
            or "map (mmhg)" in blob
        )

    def _infusion(row: dict[str, str]) -> bool:
        drug = (row.get("drugname") or "").lower()
        return any(agent in drug for agent in _VASO_AGENTS)

    return {
        "lab": lambda row: (row.get("labname") or "").strip().lower() in lab_names,
        "vital_periodic": lambda row: True,
        "vital_aperiodic": lambda row: True,
        "nurse_charting": _nurse,
        "respiratory_charting": lambda row: (
            (row.get("respchartvaluelabel") or "").strip().lower() in _RESP_FIO2_LABELS
        ),
        "intake_output": lambda row: (row.get("celllabel") or "").strip().lower() == "urine",
        "infusion_drug": _infusion,
        "physical_exam": lambda row: (
            "/gcs/" in (row.get("physicalexampath") or "").lower()
            or "glasgow" in (row.get("physicalexampath") or "").lower()
        ),
        "diagnosis": lambda row: True,
    }


_MIMIC_SPEC_ROWS = (
    (
        "lab", "hosp/labevents.csv.gz", "subject", "subject_id", "charttime",
        "storetime", "itemid", "valueuom", "value", "valuenum",
    ),
    (
        "chart", "icu/chartevents.csv.gz", "stay", "stay_id", "charttime",
        "storetime", "itemid", "valueuom", "value", "valuenum",
    ),
    (
        "input", "icu/inputevents.csv.gz", "stay", "stay_id", "starttime",
        "storetime", "itemid", "rateuom", "rate", "rate",
    ),
    (
        "output", "icu/outputevents.csv.gz", "stay", "stay_id", "charttime",
        "storetime", "itemid", "valueuom", "value", "value",
    ),
    (
        "diagnosis", "hosp/diagnoses_icd.csv.gz", "hadm", "hadm_id",
        "__dischtime__", None, "icd_code", "", "long_title", "",
    ),
)

_EICU_SPEC_ROWS = (
    ("lab", "lab.csv.gz", "labresultoffset", "labname", "labmeasurenamesystem",
     "labresult", "labresult"),
    ("vital_periodic", "vitalPeriodic.csv.gz", "observationoffset", "", "", "", ""),
    ("vital_aperiodic", "vitalAperiodic.csv.gz", "observationoffset", "", "", "", ""),
    ("nurse_charting", "nurseCharting.csv.gz", "nursingchartoffset",
     "nursingchartcelltypevallabel", "", "nursingchartvalue", "nursingchartvalue"),
    ("respiratory_charting", "respiratoryCharting.csv.gz", "respchartoffset",
     "respchartvaluelabel", "", "respchartvalue", "respchartvalue"),
    ("intake_output", "intakeOutput.csv.gz", "intakeoutputoffset", "celllabel", "",
     "cellvaluenumeric", "cellvaluenumeric"),
    ("infusion_drug", "infusionDrug.csv.gz", "infusionoffset", "drugname", "",
     "drugrate", "drugrate"),
    ("physical_exam", "physicalExam.csv.gz", "physicalexamoffset", "physicalexampath",
     "", "physicalexamvalue", "physicalexamvalue"),
    ("diagnosis", "diagnosis.csv.gz", "diagnosisoffset", "icd9code", "",
     "diagnosisstring", ""),
)


def _family_specs(dataset: str, items: str) -> list[FamilySpec]:
    if dataset not in {"mimic", "eicu"}:
        raise IndexError(f"unknown dataset {dataset!r}; expected 'mimic' or 'eicu'")
    mapped = items == "mapped"
    if dataset == "mimic":
        filters = _mimic_mapped_filters() if mapped else {}
        return [
            FamilySpec(
                family=family,
                source_file=src,
                scope=scope,
                scope_key=scope_key,
                time_key=time_key,
                availability_key=avail_key,
                itemid_key=itemid_key,
                unit_key=unit_key,
                value_raw_key=raw_key,
                value_num_key=num_key,
                mapped_filter=filters.get(family) if mapped else None,
                is_discharge_diagnosis=(family == "diagnosis"),
            )
            for (
                family, src, scope, scope_key, time_key, avail_key, itemid_key,
                unit_key, raw_key, num_key,
            ) in _MIMIC_SPEC_ROWS
        ]
    filters = _eicu_mapped_filters() if mapped else {}
    return [
        FamilySpec(
            family=family,
            source_file=src,
            scope="stay",
            scope_key="patientunitstayid",
            time_key=time_key,
            availability_key=None,
            itemid_key=itemid_key,
            unit_key=unit_key,
            value_raw_key=raw_key,
            value_num_key=num_key,
            mapped_filter=filters.get(family) if mapped else None,
        )
        for family, src, time_key, itemid_key, unit_key, raw_key, num_key in _EICU_SPEC_ROWS
    ]


# --------------------------------------------------------------------------- #
# Stay discovery
# --------------------------------------------------------------------------- #


def _stay_sort_key(stay_id: str) -> tuple[int, str]:
    if str(stay_id).isdigit():
        return (int(stay_id), "")
    return (1 << 63, str(stay_id))


def _load_mimic_stays(
    source_root: Path, limit: int
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    stays: list[dict[str, Any]] = []
    for row in _iter_csv_gz_rows(source_root / "icu" / "icustays.csv.gz"):
        stay_id = (row.get("stay_id") or "").strip()
        if not stay_id:
            continue
        stays.append(
            {
                "stay_id": stay_id,
                "subject_id": (row.get("subject_id") or "").strip(),
                "hadm_id": (row.get("hadm_id") or "").strip(),
                "intime": parse_mimic_ts(row.get("intime") or ""),
                "outtime": parse_mimic_ts(row.get("outtime") or ""),
                "dischtime": None,
                "event_count": 0,
                "extra_json": json.dumps(row, sort_keys=True, separators=(",", ":")),
            }
        )
    stays.sort(key=lambda s: _stay_sort_key(s["stay_id"]))
    disch_by_hadm: dict[str, str] = {}
    for row in _iter_csv_gz_rows(source_root / "hosp" / "admissions.csv.gz"):
        hadm = (row.get("hadm_id") or "").strip()
        if hadm:
            disch_by_hadm[hadm] = row.get("dischtime") or ""
    for stay in stays:
        stay["dischtime"] = parse_mimic_ts(disch_by_hadm.get(stay["hadm_id"] or ""))
    if limit:
        stays = stays[:limit]
    return stays, disch_by_hadm


def _load_eicu_stays(source_root: Path, limit: int) -> list[dict[str, Any]]:
    stays: list[dict[str, Any]] = []
    for row in _iter_csv_gz_rows(source_root / "patient.csv.gz"):
        stay_id = (row.get("patientunitstayid") or "").strip()
        if not stay_id:
            continue
        out_off = _to_float(row.get("unitdischargeoffset"))
        outtime = EICU_EPOCH + timedelta(minutes=out_off or 0)
        stays.append(
            {
                "stay_id": stay_id,
                "subject_id": (
                    row.get("uniquepid")
                    or row.get("patienthealthsystemstayid")
                    or stay_id
                ).strip(),
                "hadm_id": (row.get("patienthealthsystemstayid") or "").strip(),
                "intime": EICU_EPOCH,
                "outtime": outtime,
                "dischtime": None,
                "event_count": 0,
                "extra_json": json.dumps(row, sort_keys=True, separators=(",", ":")),
            }
        )
    stays.sort(key=lambda s: _stay_sort_key(s["stay_id"]))
    if limit:
        stays = stays[:limit]
    return stays


# --------------------------------------------------------------------------- #
# Row extraction (shared by build + reconcile — the equivalence guarantee)
# --------------------------------------------------------------------------- #


def extract_event(
    *,
    row: dict[str, str],
    row_ordinal: int,
    spec: FamilySpec,
    dataset: str,
    stays_by_id: dict[str, dict[str, Any]],
    subject_hadm_stays: dict[tuple[str, str], list[dict[str, Any]]],
    stay_by_hadm: dict[str, dict[str, Any]],
    subject_all_stays: dict[str, list[dict[str, Any]]],
    disch_by_hadm: dict[str, str],
) -> tuple[str, list[dict[str, Any]] | None]:
    """Map one source row to ("ok", [events]) | ("filtered"|"unassigned"|"bad_time", None).

    Subject-scoped rows (MIMIC labevents) fan out to every ICU stay of the
    matching admission, mirroring the adapter path: a lab with ``hadm_id``
    belongs to all ICU stays of that admission, and an empty ``hadm_id`` row
    belongs to every stay of the subject.
    """
    source_table = Path(spec.source_file).name.split(".csv")[0]
    target_stays: list[dict[str, Any]] = []
    hadm_id = ""
    if spec.scope == "stay":
        key = (row.get(spec.scope_key) or "").strip()
        stay = stays_by_id.get(key)
        if stay is not None:
            target_stays = [stay]
            hadm_id = stay.get("hadm_id") or ""
    elif spec.scope == "hadm":
        hadm = (row.get(spec.scope_key) or "").strip()
        stay = stay_by_hadm.get(hadm)
        if stay is not None:
            target_stays = [stay]
        hadm_id = hadm
    else:  # subject scope (MIMIC labevents: subject_id + hadm_id)
        sid = (row.get("subject_id") or "").strip()
        hadm = (row.get("hadm_id") or "").strip()
        if hadm:
            target_stays = list(subject_hadm_stays.get((sid, hadm)) or [])
        else:
            target_stays = list(subject_all_stays.get(sid) or [])
        hadm_id = hadm
    if not target_stays:
        return ("unassigned", None)

    if spec.mapped_filter is not None and not spec.mapped_filter(row):
        return ("filtered", None)

    if spec.family == "diagnosis" and dataset == "mimic":
        raw_time = disch_by_hadm.get((row.get("hadm_id") or "").strip())
        event_time = parse_mimic_ts(raw_time)
    elif dataset == "eicu":
        event_time = _eicu_offset_ts(row.get(spec.time_key))
    else:
        event_time = parse_mimic_ts(row.get(spec.time_key) or "")
    if event_time is None:
        return ("bad_time", None)

    availability = event_time
    if spec.availability_key:
        raw_avail = row.get(spec.availability_key)
        if raw_avail:
            parsed_avail = (
                _eicu_offset_ts(raw_avail)
                if dataset == "eicu"
                else parse_mimic_ts(str(raw_avail))
            )
            if parsed_avail is not None and parsed_avail > event_time:
                availability = parsed_avail

    itemid, itemid_num = _coerce_itemid(row.get(spec.itemid_key) or "")
    unit = (row.get(spec.unit_key) or "") if spec.unit_key else ""
    value_raw = (row.get(spec.value_raw_key) or "") if spec.value_raw_key else ""
    value_num = _to_float(row.get(spec.value_num_key)) if spec.value_num_key else None

    extra = json.dumps(row, sort_keys=True, separators=(",", ":"))
    events = [
        {
            "stay_id": str(stay["stay_id"]),
            "subject_id": str(stay.get("subject_id") or ""),
            "hadm_id": hadm_id,
            "event_family": spec.family,
            "event_time": event_time,
            "availability_time": availability,
            "source_table": source_table,
            "source_row": row_ordinal,
            "itemid": itemid,
            "itemid_num": itemid_num,
            "unit": unit,
            "value_raw": value_raw,
            "value_num": value_num,
            "status": "final",
            "is_discharge_diagnosis": bool(spec.is_discharge_diagnosis),
            "evidence_id": f"{dataset}/{source_table}/{row_ordinal}",
            "extra_json": extra,
        }
        for stay in target_stays
    ]
    return ("ok", events)


def _event_normalized(event: dict[str, Any]) -> dict[str, Any]:
    """Comparable form: timestamps as strings, extra_json as canonical text."""
    out = dict(event)
    out["event_time"] = _fmt_ts(event.get("event_time"))
    out["availability_time"] = _fmt_ts(event.get("availability_time"))
    extra = event.get("extra_json")
    if isinstance(extra, (dict, list)):
        out["extra_json"] = json.dumps(extra, sort_keys=True, separators=(",", ":"))
    return out


# --------------------------------------------------------------------------- #
# Parquet schemas + table IO
# --------------------------------------------------------------------------- #


def _event_schema() -> Any:
    _require_arrow()
    return pa.schema(
        [
            pa.field("stay_id", pa.string(), nullable=False),
            pa.field("subject_id", pa.string(), nullable=False),
            pa.field("hadm_id", pa.string(), nullable=False),
            pa.field("event_family", pa.string(), nullable=False),
            pa.field("event_time", pa.timestamp("ms"), nullable=False),
            pa.field("availability_time", pa.timestamp("ms"), nullable=False),
            pa.field("source_table", pa.string(), nullable=False),
            pa.field("source_row", pa.int64(), nullable=False),
            pa.field("itemid", pa.string(), nullable=False),
            pa.field("itemid_num", pa.int64(), nullable=True),
            pa.field("unit", pa.string(), nullable=False),
            pa.field("value_raw", pa.string(), nullable=True),
            pa.field("value_num", pa.float64(), nullable=True),
            pa.field("status", pa.string(), nullable=False),
            pa.field("is_discharge_diagnosis", pa.bool_(), nullable=False),
            pa.field("evidence_id", pa.string(), nullable=False),
            pa.field("extra_json", pa.string(), nullable=True),
        ]
    )


def _stays_schema() -> Any:
    _require_arrow()
    return pa.schema(
        [
            pa.field("stay_id", pa.string(), nullable=False),
            pa.field("subject_id", pa.string(), nullable=False),
            pa.field("hadm_id", pa.string(), nullable=False),
            pa.field("intime", pa.timestamp("ms"), nullable=True),
            pa.field("outtime", pa.timestamp("ms"), nullable=True),
            pa.field("dischtime", pa.timestamp("ms"), nullable=True),
            pa.field("event_count", pa.int64(), nullable=False),
            pa.field("extra_json", pa.string(), nullable=True),
        ]
    )


def _patients_schema() -> Any:
    _require_arrow()
    return pa.schema(
        [
            pa.field("subject_id", pa.string(), nullable=False),
            pa.field("anchor_age", pa.int64(), nullable=True),
            pa.field("anchor_year_group", pa.string(), nullable=True),
            pa.field("extra_json", pa.string(), nullable=True),
        ]
    )


def _load_mimic_patients(source_root: Path) -> list[dict[str, Any]]:
    """MIMIC patients subset (subject_id/anchor_age) for protocol cohort selection."""
    rows: list[dict[str, Any]] = []
    for row in _iter_csv_gz_rows(source_root / "hosp" / "patients.csv.gz"):
        sid = (row.get("subject_id") or "").strip()
        if not sid:
            continue
        age = _to_float(row.get("anchor_age"))
        rows.append(
            {
                "subject_id": sid,
                "anchor_age": int(age) if age is not None else None,
                "anchor_year_group": (row.get("anchor_year_group") or "").strip() or None,
                "extra_json": json.dumps(row, sort_keys=True, separators=(",", ":")),
            }
        )
    rows.sort(key=lambda r: _stay_sort_key(r["subject_id"]))
    return rows


def _write_table(path: Path, rows: list[dict[str, Any]], schema: Any) -> None:
    _require_arrow()
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd", data_page_version="2.0")


class _ShardPool:
    """Bounded set of open gzip JSON-L shard writers (memory-bounded builds)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.open_handles: dict[tuple[str, str], Any] = {}

    def write(self, family: str, stay_id: str, event: dict[str, Any]) -> None:
        key = (family, stay_id)
        handle = self.open_handles.get(key)
        if handle is None:
            if len(self.open_handles) >= _MAX_OPEN_SHARDS:
                self.close_all()
            dir_path = self.root / family
            dir_path.mkdir(parents=True, exist_ok=True)
            handle = gzip.open(dir_path / f"{stay_id}.jsonl.gz", "at", encoding="utf-8")
            self.open_handles[key] = handle
        payload = json.dumps(
            {
                k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v)
                for k, v in event.items()
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        handle.write(payload + "\n")

    def close_all(self) -> None:
        for handle in self.open_handles.values():
            handle.close()
        self.open_handles.clear()

    def shard_paths(self, family: str, stay_id: str) -> list[Path]:
        return sorted((self.root / family).glob(f"{stay_id}.jsonl.gz"))


def _read_shard_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            row["event_time"] = parse_mimic_ts(row["event_time"])
            row["availability_time"] = parse_mimic_ts(row["availability_time"])
            if row["event_time"] is None or row["availability_time"] is None:
                raise IndexError(f"corrupt shard row in {path}: {line!r}")
            events.append(row)
    return events


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events,
        key=lambda e: (
            e["availability_time"],
            e["event_time"],
            str(e["source_table"]),
            int(e["source_row"]),
        ),
    )


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def build_index(
    *,
    source_root: Path,
    index_dir: Path,
    dataset: str = "mimic",
    limit: int = 0,
    items: str = "mapped",
    dataset_version: str | None = None,
    extract_date: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build (or rebuild) the stay-level index. Deterministic for fixed inputs."""
    _require_arrow()
    if index_dir.exists() and not force:
        raise IndexError(f"index already exists at {index_dir}; pass --force to rebuild")
    specs = _family_specs(dataset, items)
    missing = [s.source_file for s in specs if not (source_root / s.source_file).is_file()]
    if missing:
        raise IndexError(f"missing source files under {source_root}: {missing}")

    if dataset == "mimic":
        stays, disch_by_hadm = _load_mimic_stays(source_root, limit)
        patients_rows = _load_mimic_patients(source_root)
    else:
        stays = _load_eicu_stays(source_root, limit)
        disch_by_hadm = {}
        patients_rows = []
    if not stays:
        raise IndexError(f"no stays found under {source_root}")

    stays_by_id = {s["stay_id"]: s for s in stays}
    subject_hadm_stays: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    stay_by_hadm: dict[str, dict[str, Any]] = {}
    subject_all_stays: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stay in stays:
        key = (stay["subject_id"], stay["hadm_id"])
        if key[0] and key[1]:
            subject_hadm_stays[key].append(stay)
        if stay["hadm_id"]:
            prev = stay_by_hadm.get(stay["hadm_id"])
            if prev is None or (stay["intime"] or EICU_EPOCH) < (prev["intime"] or EICU_EPOCH):
                stay_by_hadm[stay["hadm_id"]] = stay
        if stay["subject_id"]:
            subject_all_stays[stay["subject_id"]].append(stay)

    index_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{index_dir.name}.build-", dir=index_dir.parent))
    shards_root = tmp / "shards"
    shards_root.mkdir(parents=True)
    pool = _ShardPool(shards_root)

    source_files: dict[str, dict[str, Any]] = {}
    by_family_total = Counter()
    try:
        for spec in specs:
            path = source_root / spec.source_file
            rows_seen = 0
            rows_selected = 0
            timestamp_failures = 0
            unassigned_rows = 0
            units = Counter()
            for ordinal, row in enumerate(_iter_csv_gz_rows(path)):
                rows_seen += 1
                result, events = extract_event(
                    row=row,
                    row_ordinal=ordinal,
                    spec=spec,
                    dataset=dataset,
                    stays_by_id=stays_by_id,
                    subject_hadm_stays=subject_hadm_stays,
                    stay_by_hadm=stay_by_hadm,
                    subject_all_stays=subject_all_stays,
                    disch_by_hadm=disch_by_hadm,
                )
                if result == "ok":
                    assert events is not None
                    for event in events:
                        rows_selected += 1
                        by_family_total[spec.family] += 1
                        units[event["unit"]] += 1
                        stays_by_id[event["stay_id"]]["event_count"] += 1
                        pool.write(spec.family, event["stay_id"], event)
                elif result == "bad_time":
                    timestamp_failures += 1
                elif result == "unassigned":
                    unassigned_rows += 1
            source_files[spec.source_file] = {
                "sha256": file_sha256_hex(path),
                "size": path.stat().st_size,
                "mtime_iso": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "rows_seen": rows_seen,
                "rows_selected": rows_selected,
                "timestamp_failures": timestamp_failures,
                "unassigned_rows": unassigned_rows,
                "units": dict(units.most_common(_TOP_UNITS)),
            }
        pool.close_all()

        if dataset == "mimic":
            for rel in ("icu/icustays.csv.gz", "hosp/admissions.csv.gz"):
                path = source_root / rel
                if path.is_file():
                    source_files[rel] = {
                        "sha256": sha256_hex(path.read_bytes()),
                        "size": path.stat().st_size,
                        "mtime_iso": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                        "rows_seen": None,
                        "rows_selected": None,
                        "timestamp_failures": 0,
                        "unassigned_rows": 0,
                        "units": {},
                    }
        else:
            path = source_root / "patient.csv.gz"
            if path.is_file():
                source_files["patient.csv.gz"] = {
                    "sha256": sha256_hex(path.read_bytes()),
                    "size": path.stat().st_size,
                    "mtime_iso": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                    "rows_seen": len(stays),
                    "rows_selected": len(stays),
                    "timestamp_failures": 0,
                    "unassigned_rows": 0,
                    "units": {},
                }

        # Pass 2: shards → sorted per-stay parquet partitions + content hash.
        index_hasher = hashlib.sha256()
        stay_rows: list[dict[str, Any]] = []
        events_dir = tmp / "events"
        events_dir.mkdir(parents=True)
        for stay in stays:
            stay_events: list[dict[str, Any]] = []
            for spec in specs:
                for shard in pool.shard_paths(spec.family, stay["stay_id"]):
                    stay_events.extend(_read_shard_events(shard))
            stay_events = _sort_events(stay_events)
            if stay_events:
                part_dir = events_dir / f"stay_id={stay['stay_id']}"
                part_dir.mkdir(parents=True)
                _write_table(part_dir / "part-0.parquet", stay_events, _event_schema())
            stay["event_count"] = len(stay_events)
            for event in stay_events:
                index_hasher.update(_hash_event_line(stay["stay_id"], event))
            index_hasher.update(_hash_stay_line(stay))
            stay_rows.append(stay)
        index_hash = index_hasher.hexdigest()

        _write_table(
            tmp / "stays.parquet",
            [
                {
                    "stay_id": s["stay_id"],
                    "subject_id": s["subject_id"],
                    "hadm_id": s["hadm_id"],
                    "intime": s.get("intime"),
                    "outtime": s.get("outtime"),
                    "dischtime": s.get("dischtime"),
                    "event_count": s["event_count"],
                    "extra_json": s.get("extra_json"),
                }
                for s in stay_rows
            ],
            _stays_schema(),
        )

        if patients_rows:
            patients_path = source_root / "hosp" / "patients.csv.gz"
            _write_table(
                tmp / "patients.parquet",
                [
                    {
                        "subject_id": r["subject_id"],
                        "anchor_age": r.get("anchor_age"),
                        "anchor_year_group": r.get("anchor_year_group"),
                        "extra_json": r.get("extra_json"),
                    }
                    for r in patients_rows
                ],
                _patients_schema(),
            )
            source_files["hosp/patients.csv.gz"] = {
                "sha256": sha256_hex(patients_path.read_bytes()),
                "size": patients_path.stat().st_size,
                "mtime_iso": datetime.fromtimestamp(patients_path.stat().st_mtime).isoformat(),
                "rows_seen": len(patients_rows),
                "rows_selected": len(patients_rows),
                "timestamp_failures": 0,
                "unassigned_rows": 0,
                "units": {},
            }

        mtimes = [
            datetime.fromtimestamp((source_root / s.source_file).stat().st_mtime)
            for s in specs
        ]
        meta = {
            "index_schema_version": INDEX_SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
            "built_at": datetime.now().astimezone().isoformat(),
            "dataset": {
                "name": {"mimic": "mimic-iv", "eicu": "eicu-crd"}[dataset],
                "version": dataset_version or {"mimic": "3.1", "eicu": "2.0"}[dataset],
                "extract_date": extract_date or max(mtimes).strftime("%Y-%m-%d"),
            },
            "source_root": str(source_root),
            "source_files": source_files,
            "config": {"dataset": dataset, "limit": limit, "items": items},
            "stays": {
                "total": len(stays),
                "indexed": len(stays),
                "with_events": sum(1 for s in stay_rows if s["event_count"]),
            },
            "events": {"total": sum(by_family_total.values()), "by_family": dict(by_family_total)},
            "index_hash": index_hash,
            "code": _code_revision(),
        }
        (tmp / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

        shutil.rmtree(shards_root, ignore_errors=True)
        if index_dir.exists():
            shutil.rmtree(index_dir)
        os.replace(tmp, index_dir)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return meta


# --------------------------------------------------------------------------- #
# Reader
# --------------------------------------------------------------------------- #


def default_index_dir(dataset: str) -> Path:
    env_key = {"mimic": "CURIE_MIMIC_INDEX_DIR", "eicu": "CURIE_EICU_INDEX_DIR"}[dataset]
    raw = os.environ.get(env_key)
    if raw:
        return Path(raw).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "data" / "index" / {"mimic": "mimic-iv", "eicu": "eicu"}[dataset]).resolve()


def load_index_meta(index_dir: Path) -> dict[str, Any]:
    path = index_dir / "meta.json"
    if not path.is_file():
        raise IndexError(f"no index at {index_dir} (missing meta.json)")
    meta = json.loads(path.read_text())
    if meta.get("index_schema_version") != INDEX_SCHEMA_VERSION:
        raise IndexError(
            f"index schema {meta.get('index_schema_version')!r} != {INDEX_SCHEMA_VERSION}"
        )
    return meta


def load_stays(index_dir: Path) -> list[dict[str, Any]]:
    _require_arrow()
    path = index_dir / "stays.parquet"
    if not path.is_file():
        raise IndexError(f"no stays.parquet in {index_dir}")
    rows = pq.read_table(path).to_pylist()
    rows.sort(key=lambda r: _stay_sort_key(str(r["stay_id"])))
    for row in rows:
        if row.get("extra_json"):
            row["extra_json"] = json.loads(row["extra_json"])
    return rows


def stay_partition_path(index_dir: Path, stay_id: str) -> Path:
    return index_dir / "events" / f"stay_id={stay_id}" / "part-0.parquet"


def load_stay_events(index_dir: Path, stay_id: str) -> list[dict[str, Any]]:
    """Read one stay's events (stay-level partition = pushdown to one file)."""
    _require_arrow()
    path = stay_partition_path(index_dir, stay_id)
    if not path.is_file():
        return []
    rows = pq.read_table(path).to_pylist()
    for row in rows:
        if row.get("extra_json"):
            row["extra_json"] = json.loads(row["extra_json"])
    return rows


def scan_index_events(
    index_dir: Path,
    *,
    stay_ids: list[str] | None = None,
    filters: list[tuple[str, str, Any]] | None = None,
) -> Any:
    """Dataset-level scan with predicate pushdown (stay partitions + column filters)."""
    _require_arrow()
    import pyarrow.dataset as ds

    events_root = index_dir / "events"
    if not events_root.is_dir():
        raise IndexError(f"no events/ under {index_dir}")
    expression: Any = None
    for name, _op, value in filters or []:
        term = ds.field(name) == value
        expression = term if expression is None else expression & term
    if stay_ids is not None:
        term = ds.field("stay_id").isin(stay_ids)
        expression = term if expression is None else expression & term
    partitioning = ds.partitioning(
        pa.schema([pa.field("stay_id", pa.string())]), flavor="hive"
    )
    dataset = ds.dataset(events_root, format="parquet", partitioning=partitioning)
    if expression is None:
        return dataset.to_table()
    return dataset.to_table(filter=expression)


def compute_index_hash(index_dir: Path) -> str:
    """Re-derive the content hash from the on-disk index (deterministic check)."""
    _require_arrow()
    hasher = hashlib.sha256()
    stays = load_stays(index_dir)
    for stay in stays:
        for event in load_stay_events(index_dir, str(stay["stay_id"])):
            hasher.update(_hash_event_line(str(stay["stay_id"]), event))
        stay_line = dict(stay)
        if stay_line.get("extra_json") is not None:
            stay_line["extra_json"] = json.dumps(
                stay_line["extra_json"], sort_keys=True, separators=(",", ":")
            )
        hasher.update(_hash_stay_line(stay_line))
    return hasher.hexdigest()


def validate_index(
    index_dir: Path,
    *,
    order_check_limit: int = 50,
) -> dict[str, Any]:
    """Structural validation: hashes, counts, partition coverage, ordering."""
    _require_arrow()
    meta = load_index_meta(index_dir)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    stays = load_stays(index_dir)
    meta_stays = meta.get("stays") or {}
    check("stays_count", len(stays) == meta_stays.get("total"), len(stays))

    events_root = index_dir / "events"
    partitions = (
        {p.parent.name.split("=", 1)[1] for p in events_root.rglob("part-0.parquet")}
        if events_root.is_dir()
        else set()
    )
    expected = {str(s["stay_id"]) for s in stays}
    missing = expected - partitions
    extra = partitions - expected
    check(
        "stay_partition_coverage",
        not missing and not extra,
        {"missing": sorted(missing)[:10], "extra": sorted(extra)[:10]},
    )

    total_events = 0
    total_expected = int((meta.get("events") or {}).get("total") or 0)
    ordering_ok = True
    ordering_detail: dict[str, Any] = {}
    stays_with_events = 0
    for idx, stay in enumerate(stays):
        events = load_stay_events(index_dir, str(stay["stay_id"]))
        total_events += len(events)
        if events:
            stays_with_events += 1
        if stay.get("event_count") != len(events):
            check(
                "event_count_consistency",
                False,
                {
                    "stay_id": stay["stay_id"],
                    "stays_table": stay.get("event_count"),
                    "partition": len(events),
                },
            )
        if idx < order_check_limit and events:
            keys = [
                (e["availability_time"], e["event_time"], str(e["source_table"]), e["source_row"])
                for e in events
            ]
            if keys != sorted(keys):
                ordering_ok = False
                ordering_detail["stay_id"] = stay["stay_id"]
    check("event_count_total", total_events == total_expected, total_events)
    check("timestamp_ordering", ordering_ok, ordering_detail)
    check(
        "stays_with_events",
        stays_with_events == meta_stays.get("with_events"),
        stays_with_events,
    )

    index_hash = compute_index_hash(index_dir)
    check("index_hash", index_hash == meta.get("index_hash"), index_hash)

    return {
        "ok": not failures,
        "index_dir": str(index_dir),
        "index_hash": index_hash,
        "stays": len(stays),
        "events": total_events,
        "failures": failures,
        "checks": checks,
        "units_by_source_file": {
            src: dict(info.get("units") or {})
            for src, info in (meta.get("source_files") or {}).items()
        },
        "timestamp_failures": {
            src: info.get("timestamp_failures")
            for src, info in (meta.get("source_files") or {}).items()
        },
    }


def reconcile_source_to_index(
    *,
    source_root: Path,
    index_dir: Path,
    dataset: str,
    stay_ids: list[str] | None = None,
    limit: int = 25,
    seed: int = 42,
) -> dict[str, Any]:
    """Prove source/index row equivalence: re-scan source files, compare sampled stays.

    One selected source row must map to exactly one index row with identical fields.
    """
    _require_arrow()
    import random

    meta = load_index_meta(index_dir)
    specs = _family_specs(meta["config"]["dataset"], meta["config"]["items"])
    all_stays = load_stays(index_dir)
    if stay_ids:
        wanted = set(stay_ids)
        sample = [s for s in all_stays if str(s["stay_id"]) in wanted]
    else:
        rng = random.Random(seed)
        sample = rng.sample(all_stays, min(limit, len(all_stays)))
    sample_ids = {str(s["stay_id"]) for s in sample}

    stays_by_id = {s["stay_id"]: s for s in all_stays}
    subject_hadm_stays: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    stay_by_hadm: dict[str, dict[str, Any]] = {}
    subject_all_stays: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stay in all_stays:
        key = (stay["subject_id"], stay["hadm_id"])
        if key[0] and key[1]:
            subject_hadm_stays[key].append(stay)
        if stay["hadm_id"]:
            prev = stay_by_hadm.get(stay["hadm_id"])
            if prev is None or (stay["intime"] or EICU_EPOCH) < (prev["intime"] or EICU_EPOCH):
                stay_by_hadm[stay["hadm_id"]] = stay
        if stay["subject_id"]:
            subject_all_stays[stay["subject_id"]].append(stay)

    disch_by_hadm: dict[str, str] = {}
    if dataset == "mimic":
        for row in _iter_csv_gz_rows(source_root / "hosp" / "admissions.csv.gz"):
            hadm = (row.get("hadm_id") or "").strip()
            if hadm:
                disch_by_hadm[hadm] = row.get("dischtime") or ""

    index_rows: dict[str, dict[str, dict[int, dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for stay in sample:
        for event in load_stay_events(index_dir, str(stay["stay_id"])):
            stay_key = str(stay["stay_id"])
            index_rows[stay_key][event["event_family"]][int(event["source_row"])] = event

    report_files: dict[str, dict[str, Any]] = {}
    mismatches: list[dict[str, Any]] = []
    rows_compared = 0
    ok = True
    for spec in specs:
        path = source_root / spec.source_file
        seen = 0
        matched = 0
        file_ok = True
        seen_ordinals: dict[str, set[int]] = defaultdict(set)
        for ordinal, row in enumerate(_iter_csv_gz_rows(path)):
            result, events = extract_event(
                row=row,
                row_ordinal=ordinal,
                spec=spec,
                dataset=dataset,
                stays_by_id=stays_by_id,
                subject_hadm_stays=subject_hadm_stays,
                stay_by_hadm=stay_by_hadm,
                subject_all_stays=subject_all_stays,
                disch_by_hadm=disch_by_hadm,
            )
            if result != "ok" or events is None:
                continue
            for event in events:
                if event["stay_id"] not in sample_ids:
                    continue
                seen += 1
                seen_ordinals[event["stay_id"]].add(ordinal)
                indexed = index_rows[event["stay_id"]][spec.family].get(ordinal)
                if indexed is None:
                    file_ok = False
                    mismatches.append(
                        {
                            "file": spec.source_file,
                            "stay_id": event["stay_id"],
                            "source_row": ordinal,
                            "issue": "missing_from_index",
                        }
                    )
                    continue
                if _event_normalized(indexed) == _event_normalized(event):
                    matched += 1
                    rows_compared += 1
                else:
                    file_ok = False
                    diff = {
                        k: (indexed.get(k), event[k])
                        for k in EVENT_SCHEMA_KEYS
                        if indexed.get(k) != event[k]
                    }
                    mismatches.append(
                        {
                            "file": spec.source_file,
                            "stay_id": event["stay_id"],
                            "source_row": ordinal,
                            "issue": "field_mismatch",
                            "diff": {k: str(v) for k, v in diff.items()},
                        }
                    )
        for stay_id, by_family in index_rows.items():
            for row_no in by_family.get(spec.family, {}):
                if row_no not in seen_ordinals.get(stay_id, set()):
                    file_ok = False
                    mismatches.append(
                        {
                            "file": spec.source_file,
                            "stay_id": stay_id,
                            "source_row": row_no,
                            "issue": "missing_from_source",
                        }
                    )
        digest = file_sha256_hex(path)
        expected_hash = (meta.get("source_files") or {}).get(spec.source_file, {}).get("sha256")
        hash_ok = digest == expected_hash
        report_files[spec.source_file] = {
            "sha256_matches": bool(hash_ok),
            "rows_seen": seen,
            "rows_matched": matched,
            "file_ok": bool(file_ok and hash_ok),
        }
        ok = ok and file_ok and hash_ok

    return {
        "ok": bool(ok),
        "index_dir": str(index_dir),
        "source_root": str(source_root),
        "stays_sampled": len(sample),
        "rows_compared": rows_compared,
        "mismatches": mismatches[:50],
        "mismatch_count": len(mismatches),
        "source_files": report_files,
    }
