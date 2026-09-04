"""MIMIC-IV Clinical Database Demo CSVs → demo-schema stays."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ingestion.adapters.demo_schema import downsample_hourly
from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.loader import (
    index_chartevents,
    index_labevents,
    load_icustays,
)
from ingestion.adapters.mimic.paths import require_mimic_demo_dir
from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu.convert import _emit_stay

SCHEMA_VERSION = "1.0.0"

_LAB_ITEMID_CONCEPT = {
    **{i: c.CREATININE for i in im.LAB_CREATININE},
    **{i: c.PLATELETS for i in im.LAB_PLATELETS},
    **{i: c.BILIRUBIN_TOTAL for i in im.LAB_BILIRUBIN_TOTAL},
}

_CHART_ITEMID_CONCEPT = {
    **{i: c.MAP for i in im.CHART_MAP | {220181}},
    **{i: c.SPO2 for i in im.CHART_SPO2},
    **{i: c.FIO2 for i in im.CHART_FIO2},
    **{i: c.GCS_EYE for i in im.CHART_GCS_EYE},
    **{i: c.GCS_VERBAL for i in im.CHART_GCS_VERBAL},
    **{i: c.GCS_MOTOR for i in im.CHART_GCS_MOTOR},
    **{i: c.CREATININE for i in im.CHART_CREATININE},
    **{i: c.BILIRUBIN_TOTAL for i in im.CHART_BILIRUBIN},
    **{i: c.PLATELETS for i in im.CHART_PLATELETS},
}


def convert_mimic_demo(root: Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    root = root or require_mimic_demo_dir()
    stays_raw = load_icustays(root, limit=limit)
    subject_ids = {s["subject_id"] for s in stays_raw}
    stay_ids = {s["stay_id"] for s in stays_raw}

    labs_by_subject = index_labevents(
        root, subject_ids=subject_ids, itemids=set(_LAB_ITEMID_CONCEPT)
    )
    charts_by_stay = index_chartevents(
        root, stay_ids=stay_ids, itemids=set(_CHART_ITEMID_CONCEPT)
    )

    counts: dict[str, int] = defaultdict(int)
    stays: list[dict[str, Any]] = []
    for stay in stays_raw:
        stay_id = stay["stay_id"]
        sid = stay["subject_id"]
        hadm = stay.get("hadm_id") or ""
        lab_events: list[dict[str, Any]] = []
        for row in labs_by_subject.get(sid, []):
            if hadm and row.get("hadm_id") not in {"", hadm}:
                continue
            concept = _LAB_ITEMID_CONCEPT.get(int(row["itemid"]))
            if concept is None:
                continue
            lab_events.append(
                {
                    "concept": concept,
                    "itemid": row["itemid"],
                    "valuenum": row["valuenum"],
                    "unit": "",
                    "charttime": row["charttime"],
                    "storetime": row["charttime"],
                }
            )
            counts[concept] += 1
        chart_events: list[dict[str, Any]] = []
        for row in charts_by_stay.get(stay_id, []):
            concept = _CHART_ITEMID_CONCEPT.get(int(row["itemid"]))
            if concept is None:
                continue
            chart_events.append(
                {
                    "concept": concept,
                    "itemid": row["itemid"],
                    "valuenum": row["valuenum"],
                    "unit": "",
                    "charttime": row["charttime"],
                    "storetime": row["charttime"],
                }
            )
            counts[concept] += 1
        stays.append(
            _emit_stay(
                stay_meta={
                    "stay_id": stay_id,
                    "subject_id": sid,
                    "hadm_id": hadm,
                    "intime": stay.get("intime"),
                    "outtime": stay.get("outtime"),
                },
                lab_events=downsample_hourly(lab_events),
                chart_events=downsample_hourly(chart_events),
                diagnoses=[],
                evidence_prefix="mimic",
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_pin": {
            "name": "mimic-iv-clinical-database-demo",
            "version": "2.2",
            "note": (
                "Open PhysioNet MIMIC-IV demo CSVs. Snapshot `make mimic-demo` is "
                "the original scorer; this conversion feeds the timeline harness. "
                "No outcome labels."
            ),
        },
        "coverage": {"concepts": dict(counts), "stays": len(stays)},
        "stays": stays,
        "warnings": [],
    }
