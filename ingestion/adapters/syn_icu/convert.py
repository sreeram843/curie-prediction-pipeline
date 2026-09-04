"""Convert SYN-ICU tables → demo-schema-stays fixture shape.

The output matches `eval/fixtures/mimic_harness/demo_schema_stays.v1.json`, so
the leakage-safe harness (`eval/mimic_harness.replay`) scores SYN-ICU stays
unchanged. SYN-ICU is synthetic and has no ground-truth labels — labels are
emitted as ``None`` and never fabricated.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ingestion.adapters.syn_icu import concepts as c
from ingestion.adapters.syn_icu import reader
from ingestion.adapters.syn_icu.paths import require_syn_icu_dir

SCHEMA_VERSION = "1.0.0"

_LAB_CONCEPTS = {c.CREATININE, c.PLATELETS, c.BILIRUBIN_TOTAL}
_CHART_CONCEPTS = {
    c.MAP,
    c.SPO2,
    c.FIO2,
    c.GCS_EYE,
    c.GCS_VERBAL,
    c.GCS_MOTOR,
    c.GCS_TOTAL,
    c.CREATININE,
    c.PLATELETS,
    c.BILIRUBIN_TOTAL,
}

_LOINC_BY_CONCEPT = {
    c.CREATININE: c.CREATININE_LOINC,
    c.PLATELETS: c.PLATELETS_LOINC,
    c.BILIRUBIN_TOTAL: c.BILIRUBIN_LOINC,
    c.MAP: c.MAP_LOINC,
    c.SPO2: c.SPO2_LOINC,
    c.FIO2: c.FIO2_LOINC,
    c.GCS_TOTAL: c.GCS_LOINC,
}

_DISPLAY_BY_CONCEPT = {
    c.CREATININE: "Creatinine",
    c.PLATELETS: "Platelets",
    c.BILIRUBIN_TOTAL: "Total Bilirubin",
    c.MAP: "MAP",
    c.SPO2: "SpO2",
    c.FIO2: "FiO2",
    c.GCS_TOTAL: "GCS",
}


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _ts_str(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(raw, date):
        return raw.strftime("%Y-%m-%d %H:%M:%S")
    text = str(raw).strip()
    return text or None


def _get(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None and str(row[key]).strip() != "":
            return row[key]
    return None


def load_concept_index(root: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    d_items = reader.read_table(root, "syn_d_items")
    d_labitems = reader.read_table(root, "syn_d_labitems")
    return c.build_concept_index(d_labitems=d_labitems, d_items=d_items)


def _index_events(
    root: Path,
    table: str,
    *,
    itemid_to_concept: dict[str, str],
    stay_id_to_key: dict[str, dict[str, Any]],
    wanted: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Stream a SYN-ICU event table once, indexing rows by stay_id and subject_id.

    Returns ``(stay_events, concept_counts)``. ``stay_events`` maps stay_id →
    list of ``{concept, itemid, valuenum, unit, charttime, storetime}``.
    """
    stay_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    concept_counts: dict[str, int] = defaultdict(int)
    # stay_id → subject_id, and subject_id → [stay_ids] for subject-scoped tables.
    subject_to_stays: dict[str, list[str]] = defaultdict(list)
    for stay_id, meta in stay_id_to_key.items():
        subject_to_stays[str(meta["subject_id"])].append(stay_id)

    for row in reader.iter_table(root, table):
        itemid = str(_get(row, "itemid") or "").strip()
        concept = itemid_to_concept.get(itemid)
        if concept is None or concept not in wanted:
            continue
        valuenum = _to_float(_get(row, "valuenum"))
        if valuenum is None:
            continue
        charttime = _ts_str(_get(row, "charttime"))
        if charttime is None:
            continue

        event = {
            "concept": concept,
            "itemid": itemid,
            "valuenum": valuenum,
            "unit": str(_get(row, "valueuom") or ""),
            "charttime": charttime,
            "storetime": _ts_str(_get(row, "storetime")),
        }
        # chartevents/outputevents are stay-scoped; labevents are subject-scoped.
        raw_stay = _get(row, "stay_id", "icustay_id")
        if raw_stay is not None and str(raw_stay) in stay_id_to_key:
            stay_events[str(raw_stay)].append(event)
            concept_counts[concept] += 1
        else:
            sid = str(_get(row, "subject_id") or "")
            if sid in subject_to_stays:
                for stay_id in subject_to_stays[sid]:
                    stay_events[stay_id].append(event)
                concept_counts[concept] += 1

    return stay_events, concept_counts


def _gcs_and_respiration(
    chart_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reduce raw GCS and SpO2/FiO2 chart rows into scalar observations.

    GCS eye/verbal/motor are summed when aligned by timestamp; a ``gcs_total``
    row passes through directly. SpO2 + FiO2 at the same timestamp become a
    SpO2/FiO2 ratio (unit ``ratio``); lone SpO2 becomes a percent observation.
    """
    gcs_by_ts: dict[str, dict[str, float]] = defaultdict(dict)
    gcs_total_rows: list[dict[str, Any]] = []
    resp_by_ts: dict[str, dict[str, float]] = defaultdict(dict)
    others: list[dict[str, Any]] = []

    for ev in chart_events:
        concept = ev["concept"]
        if concept in {c.GCS_EYE, c.GCS_VERBAL, c.GCS_MOTOR}:
            gcs_by_ts[ev["charttime"]][concept] = ev["valuenum"]
        elif concept == c.GCS_TOTAL:
            gcs_total_rows.append(ev)
        elif concept in {c.SPO2, c.FIO2}:
            resp_by_ts[ev["charttime"]][concept] = ev["valuenum"]
        else:
            others.append(ev)

    out: list[dict[str, Any]] = list(others)

    for ts in sorted(gcs_by_ts):
        parts = gcs_by_ts[ts]
        if all(k in parts for k in (c.GCS_EYE, c.GCS_VERBAL, c.GCS_MOTOR)):
            total = parts[c.GCS_EYE] + parts[c.GCS_VERBAL] + parts[c.GCS_MOTOR]
            out.append(
                {
                    "concept": c.GCS_TOTAL,
                    "itemid": "gcs-sum",
                    "valuenum": total,
                    "unit": "",
                    "charttime": ts,
                    "storetime": None,
                }
            )
    for ev in gcs_total_rows:
        out.append(ev)

    for ts in sorted(resp_by_ts):
        parts = resp_by_ts[ts]
        if c.SPO2 in parts and c.FIO2 in parts and parts[c.FIO2] > 0:
            ratio = parts[c.SPO2] / (parts[c.FIO2] / 100.0)
            out.append(
                {
                    "concept": c.SPO2,
                    "itemid": "spo2-fio2",
                    "valuenum": round(ratio, 4),
                    "unit": "ratio",
                    "charttime": ts,
                    "storetime": None,
                }
            )
        elif c.SPO2 in parts:
            out.append(
                {
                    "concept": c.SPO2,
                    "itemid": "spo2-only",
                    "valuenum": parts[c.SPO2],
                    "unit": "%",
                    "charttime": ts,
                    "storetime": None,
                }
            )

    out.sort(key=lambda e: (e["charttime"], str(e["itemid"])))
    return out


def _emit_stay(
    *,
    stay_meta: dict[str, Any],
    lab_events: list[dict[str, Any]],
    chart_events: list[dict[str, Any]],
    diagnoses: list[dict[str, Any]],
    evidence_prefix: str = "syn",
) -> dict[str, Any]:
    stay_id = stay_meta["stay_id"]
    subject_id = stay_meta["subject_id"]
    hadm_id = stay_meta.get("hadm_id") or ""

    labs: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []

    lab_rows = sorted(
        [e for e in lab_events if e["concept"] in _LAB_CONCEPTS],
        key=lambda e: (e["charttime"], str(e["itemid"])),
    )
    for seq, ev in enumerate(lab_rows):
        concept = ev["concept"]
        labs.append(
            {
                "itemid": ev["itemid"],
                "code": _LOINC_BY_CONCEPT[concept],
                "display": _DISPLAY_BY_CONCEPT[concept],
                "valuenum": ev["valuenum"],
                "unit": ev["unit"],
                "charttime": ev["charttime"],
                "storetime": ev["storetime"] or ev["charttime"],
                "evidence_id": f"{evidence_prefix}/{stay_id}/lab/{seq}",
            }
        )

    chart_rows = _gcs_and_respiration(
        [e for e in chart_events if e["concept"] in _CHART_CONCEPTS]
    )
    for seq, ev in enumerate(chart_rows):
        concept = ev["concept"]
        if concept in {c.GCS_EYE, c.GCS_VERBAL, c.GCS_MOTOR, c.FIO2}:
            continue
        charts.append(
            {
                "itemid": ev["itemid"],
                "code": _LOINC_BY_CONCEPT[concept],
                "display": _DISPLAY_BY_CONCEPT[concept],
                "valuenum": ev["valuenum"],
                "unit": ev["unit"],
                "charttime": ev["charttime"],
                "evidence_id": f"{evidence_prefix}/{stay_id}/chart/{seq}",
            }
        )

    conditions: list[dict[str, Any]] = []
    dischtime = stay_meta.get("dischtime") or stay_meta.get("outtime")
    for seq, dx in enumerate(diagnoses):
        code = _get(dx, "icd_code", "icd10_code")
        if code is None:
            continue
        conditions.append(
            {
                "code": str(code),
                "display": str(_get(dx, "long_title") or ""),
                "onset": dischtime,
                "availability_time": dischtime,
                "is_discharge_diagnosis": True,
                "evidence_id": f"{evidence_prefix}/{stay_id}/dx/{seq}",
            }
        )

    return {
        "stay_id": stay_id,
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "split_id": stay_meta.get("split_id"),
        "intime": stay_meta.get("intime"),
        "outtime": stay_meta.get("outtime"),
        "labels": {"sepsis3_onset": None, "aki_kdigo_stage_ge_1": None},
        "labs": labs,
        "charts": charts,
        "conditions": conditions,
    }


def convert_syn_icu(
    root: Path | None = None,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build a demo-schema-stays fixture from SYN-ICU tables.

    Returns a dict with ``schema_version``, ``dataset_pin``, ``coverage``,
    ``stays``, and ``warnings``.
    """
    root = root or require_syn_icu_dir()
    itemid_to_concept, concept_to_itemids = load_concept_index(root)

    stays_meta: dict[str, dict[str, Any]] = {}
    for row in reader.iter_table(root, "syn_icustays"):
        stay_id = str(_get(row, "stay_id", "icustay_id") or "").strip()
        if not stay_id:
            continue
        subject_id = str(_get(row, "subject_id") or "").strip()
        if not subject_id:
            continue
        stays_meta[stay_id] = {
            "stay_id": stay_id,
            "subject_id": subject_id,
            "hadm_id": str(_get(row, "hadm_id") or "").strip(),
            "intime": _ts_str(_get(row, "intime")),
            "outtime": _ts_str(_get(row, "outtime")),
        }
        if limit is not None and len(stays_meta) >= limit:
            break

    # Attach discharge time from admissions for diagnosis availability.
    adm_by_hadm: dict[str, dict[str, Any]] = {}
    for row in reader.iter_table(root, "syn_admissions"):
        hadm = str(_get(row, "hadm_id") or "").strip()
        if hadm:
            adm_by_hadm[hadm] = row
    for meta in stays_meta.values():
        adm = adm_by_hadm.get(meta["hadm_id"])
        if adm:
            meta["dischtime"] = _ts_str(_get(adm, "dischtime"))

    lab_stay_events, lab_counts = _index_events(
        root,
        "syn_labevents",
        itemid_to_concept=itemid_to_concept,
        stay_id_to_key=stays_meta,
        wanted=_LAB_CONCEPTS,
    )
    chart_stay_events, chart_counts = _index_events(
        root,
        "syn_chartevents",
        itemid_to_concept=itemid_to_concept,
        stay_id_to_key=stays_meta,
        wanted=_CHART_CONCEPTS,
    )

    # Discharge diagnoses per hadm_id.
    diag_by_hadm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reader.iter_table(root, "syn_diagnoses_icd"):
        hadm = str(_get(row, "hadm_id") or "").strip()
        if hadm in adm_by_hadm:
            diag_by_hadm[hadm].append(row)

    stays = [
        _emit_stay(
            stay_meta=meta,
            lab_events=lab_stay_events.get(meta["stay_id"], []),
            chart_events=chart_stay_events.get(meta["stay_id"], []),
            diagnoses=diag_by_hadm.get(meta["hadm_id"], []),
        )
        for meta in stays_meta.values()
    ]

    warnings: list[str] = []
    for concept in sorted(_LAB_CONCEPTS | _CHART_CONCEPTS):
        if concept not in concept_to_itemids:
            warnings.append(f"No d_items/d_labitems mapped to concept '{concept}'")

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_pin": {
            "name": "syn-icu",
            "version": "khdp-syn-icu",
            "note": (
                "Synthetic GAN-generated Korean ICU data (K-MIMIC). Plumbing only; "
                "not clinical evidence."
            ),
        },
        "coverage": {
            "lab_concepts": lab_counts,
            "chart_concepts": chart_counts,
            "mapped_itemids": {k: sorted(v) for k, v in concept_to_itemids.items()},
        },
        "stays": stays,
        "warnings": warnings,
    }
