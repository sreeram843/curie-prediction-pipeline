"""MIMIC-IV Clinical Database Demo CSVs → demo-schema stays."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ingestion.adapters.demo_schema import downsample_hourly
from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.loader import (
    index_chartevents,
    index_chartevents_weights,
    index_inputevents_pressors,
    index_labevents,
    index_outputevents_urine,
    load_icustays,
)
from ingestion.adapters.mimic.paths import require_mimic_demo_dir
from ingestion.adapters.mimic.vasopressors import (
    PressorDose,
    convert_pressor_dose,
    is_bolus_order_category,
    latest_weight_before,
)
from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu.convert import _emit_stay

SCHEMA_VERSION = "1.0.0"
_PREFIX = "mimic"


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _weight_rows_for_stay(
    rows: list[dict[str, Any]],
) -> list[tuple[datetime, int, float]]:
    out: list[tuple[datetime, int, float]] = []
    for row in rows:
        t = _parse_ts(row.get("charttime"))
        if t is None:
            continue
        out.append((t, int(row["itemid"]), float(row["valuenum"])))
    return out

_LAB_ITEMID_CONCEPT = {
    **{i: c.CREATININE for i in im.LAB_CREATININE},
    **{i: c.PLATELETS for i in im.LAB_PLATELETS},
    **{i: c.BILIRUBIN_TOTAL for i in im.LAB_BILIRUBIN_TOTAL},
    **{i: c.PAO2 for i in im.LAB_PAO2},
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


def convert_mimic_demo(
    root: Path | None = None,
    *,
    limit: int | None = None,
    stays: list[dict[str, str]] | None = None,
    apply_protocol_cohort: bool = False,
    sample_seed: int = 42,
) -> dict[str, Any]:
    """Convert MIMIC ICU stays to demo-schema.

    Pass ``stays`` to convert an explicit stay list (e.g. protocol sample).
    When ``apply_protocol_cohort`` is true and ``stays`` is None, draw a seeded
    adult/first-stay/LOS≥4h sample of size ``limit`` (CURIE-049).
    """
    root = root or require_mimic_demo_dir()
    if stays is None:
        if apply_protocol_cohort:
            from ingestion.completeness import sample_mimic_protocol_stays

            if limit is None:
                raise ValueError("limit is required when apply_protocol_cohort=True")
            stays_raw = sample_mimic_protocol_stays(root, limit=limit, seed=sample_seed)
        else:
            stays_raw = load_icustays(root, limit=limit)
    else:
        stays_raw = list(stays)
        if limit is not None:
            stays_raw = stays_raw[:limit]

    subject_ids = {s["subject_id"] for s in stays_raw}
    stay_ids = {s["stay_id"] for s in stays_raw}

    labs_by_subject = index_labevents(
        root, subject_ids=subject_ids, itemids=set(_LAB_ITEMID_CONCEPT)
    )
    charts_by_stay = index_chartevents(
        root, stay_ids=stay_ids, itemids=set(_CHART_ITEMID_CONCEPT)
    )
    urine_by_stay = index_outputevents_urine(
        root, stay_ids=stay_ids, itemids=im.OUTPUT_URINE
    )
    pressors_by_stay = index_inputevents_pressors(
        root, stay_ids=stay_ids, itemids=set(im.INPUT_VASOPRESSORS)
    )
    weights_by_stay = index_chartevents_weights(root, stay_ids=stay_ids)

    counts: dict[str, int] = defaultdict(int)
    out_stays: list[dict[str, Any]] = []
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
        for row in urine_by_stay.get(stay_id, []):
            chart_events.append(
                {
                    "concept": c.URINE_OUTPUT,
                    "itemid": row["itemid"],
                    "valuenum": row["value"],
                    "unit": "mL",
                    "charttime": row["charttime"],
                    "storetime": row["charttime"],
                }
            )
            counts[c.URINE_OUTPUT] += 1
        for row in pressors_by_stay.get(stay_id, []):
            agent = im.INPUT_VASOPRESSORS.get(int(row["itemid"]))
            if agent is None:
                continue
            start = _parse_ts(row.get("starttime"))
            weight = latest_weight_before(
                weight_rows=_weight_rows_for_stay(
                    weights_by_stay.get(stay_id, [])
                ),
                as_of=start,
            ) if start is not None else None
            rate = row.get("rate")
            if is_bolus_order_category(row.get("ordercategoryname")):
                conv = PressorDose(
                    None,
                    False,
                    "bolus_order_dose_not_applicable",
                    row.get("rateuom") or None,
                    source_rate=rate,
                    evidence_id=f"MIMIC/inputevents/{row['itemid']}/{row.get('starttime')}",
                    agent=agent,
                )
            else:
                conv = convert_pressor_dose(
                    rate=rate,
                    rate_uom=row.get("rateuom") or None,
                    weight_kg=weight.weight_kg if weight else None,
                    weight_available=bool(weight and weight.status == "resolved"),
                    weight_evidence_id=weight.evidence_id if weight else None,
                    evidence_id=f"MIMIC/inputevents/{row['itemid']}/{row.get('starttime')}",
                    agent=agent,
                )
            chart_events.append(
                {
                    "concept": c.VASOPRESSOR,
                    "itemid": str(row["itemid"]),
                    "valuenum": conv.dose_ug_kg_min if conv.known else None,
                    "unit": "mcg/kg/min" if conv.known else (conv.source_unit or "unknown"),
                    "charttime": row["starttime"],
                    "storetime": row["starttime"],
                    "display": agent,
                    "evidence_id": (
                        f"{_PREFIX}/{stay_id}/input/{row['itemid']}/{row.get('starttime')}"
                    ),
                    "extras": {
                        "pressor": {
                            "known": conv.known,
                            "reason": conv.reason,
                            "source_unit": conv.source_unit,
                            "source_rate": conv.source_rate,
                            "weight_kg": conv.weight_kg,
                            "weight_evidence_id": conv.weight_evidence_id,
                            "source_row": conv.evidence_id,
                        }
                    },
                }
            )
            counts[c.VASOPRESSOR] += 1
        out_stays.append(
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

    pin_name = "mimic-iv-clinical-database-demo"
    pin_version = "2.2"
    pin_note = (
        "Open PhysioNet MIMIC-IV demo CSVs. Snapshot `make mimic-demo` is "
        "the original scorer; this conversion feeds the timeline harness. "
        "No outcome labels."
    )
    if (root / "hosp" / "labevents.csv.gz").stat().st_size > 50_000_000:
        pin_name = "mimic-iv"
        pin_version = "3.1"
        pin_note = (
            "Credentialed MIMIC-IV CSVs via demo-schema harness path. "
            "Plumbing coverage only — not Stage B clinical validation."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_pin": {
            "name": pin_name,
            "version": pin_version,
            "note": pin_note,
        },
        "coverage": {"concepts": dict(counts), "stays": len(out_stays)},
        "stays": out_stays,
        "warnings": [],
    }
