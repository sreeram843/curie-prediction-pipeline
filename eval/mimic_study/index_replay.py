"""Availability-time replay over the stay-level index (Phase C2).

One code path serves a single stay, a bounded multi-stay run, and the full
credentialed run: resolve stay ids → load per-stay Parquet partitions → emit
demo-schema stays (same concept maps and aggregation as the source-scanning
adapters, but with source-row-anchored evidence ids and preserved storetime) →
replay through the leakage-safe harness (`eval.mimic_harness.replay`).

Labels are never loaded here; see `eval.mimic_study.labels`.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import replay_stay, result_to_public_dict
from eval.mimic_study.completeness_check import sofa_component_missing_rates
from eval.mimic_study.indexing import (
    IndexError,
    load_index_meta,
    load_stay_events,
    load_stays,
    sha256_hex,
)
from ingestion.adapters.demo_schema import downsample_hourly
from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.timeline import parse_mimic_ts

REPLAY_VERSION = "0.1.0"


def _ts(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _lab_concept_map() -> dict[int, str]:
    from ingestion.adapters.mimic.to_demo_schema import _LAB_ITEMID_CONCEPT

    return dict(_LAB_ITEMID_CONCEPT)


def _chart_concept_map() -> dict[int, str]:
    from ingestion.adapters.mimic.to_demo_schema import _CHART_ITEMID_CONCEPT

    return dict(_CHART_ITEMID_CONCEPT)


def _emit_indexed_stay(
    *,
    stay_meta: dict[str, Any],
    lab_events: list[dict[str, Any]],
    chart_events: list[dict[str, Any]],
    diagnoses: list[dict[str, Any]],
    evidence_prefix: str,
) -> dict[str, Any]:
    """Mirror `syn_icu.convert._emit_stay` but preserve source-row evidence ids.

    Concept mapping, GCS merging, hourly urine summing and respiration
    resolution are identical to the source-scanning path (Phase B semantics).
    """
    from ingestion.adapters.respiration import resolve_spo2_fio2_pao2
    from ingestion.adapters.syn_icu import concepts as c
    from ingestion.adapters.syn_icu.convert import (
        _CHART_CONCEPTS,
        _DISPLAY_BY_CONCEPT,
        _LAB_CONCEPTS,
        _LOINC_BY_CONCEPT,
        _gcs_and_respiration,
        _latest_demo_observation,
        _sum_urine_by_hour,
    )

    stay_id = stay_meta["stay_id"]
    subject_id = stay_meta["subject_id"]
    hadm_id = stay_meta.get("hadm_id") or ""

    labs: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []

    lab_rows = sorted(
        [e for e in lab_events if e["concept"] in _LAB_CONCEPTS],
        key=lambda e: (str(e["charttime"]), str(e["itemid"])),
    )
    for ev in lab_rows:
        labs.append(
            {
                "itemid": ev["itemid"],
                "code": _LOINC_BY_CONCEPT[ev["concept"]],
                "display": _DISPLAY_BY_CONCEPT[ev["concept"]],
                "valuenum": ev["valuenum"],
                "unit": ev["unit"],
                "charttime": ev["charttime"],
                "storetime": ev["storetime"] or ev["charttime"],
                "evidence_id": ev["evidence_id"],
            }
        )

    chart_src = [e for e in chart_events if e["concept"] in _CHART_CONCEPTS]
    urine = [e for e in chart_src if e["concept"] == c.URINE_OUTPUT]
    other = [e for e in chart_src if e["concept"] != c.URINE_OUTPUT]
    chart_rows = _gcs_and_respiration(other) + _sum_urine_by_hour(urine)
    for ev in chart_rows:
        concept = ev["concept"]
        if concept in {c.GCS_EYE, c.GCS_VERBAL, c.GCS_MOTOR}:
            continue
        evidence_id = ev.get("evidence_id") or (
            f"{evidence_prefix}/{stay_id}/chart-merged/{ev['charttime']}"
        )
        charts.append(
            {
                "itemid": ev["itemid"],
                "code": _LOINC_BY_CONCEPT[concept],
                "display": ev.get("display") or _DISPLAY_BY_CONCEPT[concept],
                "valuenum": ev["valuenum"],
                "unit": ev["unit"],
                "charttime": ev["charttime"],
                "evidence_id": evidence_id,
                "extras": ev.get("extras") or {},
            }
        )

    as_of = parse_mimic_ts(str(stay_meta.get("outtime") or ""))
    spo2, spo2_at, spo2_eid = _latest_demo_observation(charts, code=c.SPO2_LOINC, as_of=as_of)
    fio2_pct, fio2_at, fio2_eid = _latest_demo_observation(charts, code=c.FIO2_LOINC, as_of=as_of)
    pao2, pao2_at, pao2_eid = _latest_demo_observation(labs, code=c.PAO2_LOINC, as_of=as_of)
    resolved = resolve_spo2_fio2_pao2(
        pao2_mmhg=pao2,
        pao2_observed_at=pao2_at,
        pao2_evidence_id=pao2_eid,
        spo2_percent=spo2,
        spo2_observed_at=spo2_at,
        spo2_evidence_id=spo2_eid,
        fio2_fraction=(fio2_pct / 100.0) if fio2_pct and fio2_pct > 0 else None,
        fio2_observed_at=fio2_at,
        fio2_evidence_id=fio2_eid,
        as_of=as_of,
    )

    conditions: list[dict[str, Any]] = []
    dischtime = stay_meta.get("dischtime") or stay_meta.get("outtime")
    for dx in diagnoses:
        code = dx.get("icd_code")
        if not code:
            continue
        conditions.append(
            {
                "code": str(code),
                "display": str(dx.get("long_title") or ""),
                "onset": _ts(dischtime),
                "availability_time": _ts(dischtime),
                "is_discharge_diagnosis": True,
                "evidence_id": dx.get("evidence_id") or f"{evidence_prefix}/{stay_id}/dx",
            }
        )

    return {
        "stay_id": stay_id,
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "intime": _ts(stay_meta.get("intime")),
        "outtime": _ts(stay_meta.get("outtime")),
        "labels": {"sepsis3_onset": None, "aki_kdigo_stage_ge_1": None},
        "labs": labs,
        "charts": charts,
        "conditions": conditions,
        "respiration_resolution": {
            "source": resolved.source,
            "evidence_ids": list(resolved.evidence_ids),
        },
    }


def mimic_stay_from_index(index_dir: Path, stay_row: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct one demo-schema stay from its index partition (MIMIC-IV).

    Rows are processed in source-file order per family (source_row ascending),
    mirroring the source-scanning adapter so downstream aggregation
    (downsample tie-breaks, GCS merging, weight tie-breaks) is identical.
    """
    from ingestion.adapters.mimic.vasopressors import (
        WEIGHT_ITEMIDS,
        convert_pressor_dose,
        latest_weight_before,
    )
    from ingestion.adapters.syn_icu import concepts as c

    lab_map = _lab_concept_map()
    chart_map = _chart_concept_map()
    stay_id = str(stay_row["stay_id"])
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in load_stay_events(index_dir, stay_id):
        by_family[event["event_family"]].append(event)
    for rows in by_family.values():
        rows.sort(key=lambda e: int(e["source_row"]))

    lab_events: list[dict[str, Any]] = []
    chart_events: list[dict[str, Any]] = []
    pressor_rows: list[tuple[datetime, Any, Any]] = []
    weight_rows: list[tuple[datetime, int, float]] = []
    diagnoses: list[dict[str, Any]] = []
    for event in by_family.get("lab", []):
        concept = lab_map.get(event["itemid_num"]) if event["itemid_num"] is not None else None
        if concept is None or event["value_num"] is None:
            continue
        availability = event["availability_time"]
        lab_events.append(
            {
                "concept": concept,
                "itemid": event["itemid_num"]
                if event["itemid_num"] is not None
                else event["itemid"],
                "valuenum": event["value_num"],
                "unit": event["unit"],
                "charttime": _ts(event["event_time"]),
                "storetime": (
                    _ts(availability)
                    if availability > event["event_time"]
                    else _ts(event["event_time"])
                ),
                "evidence_id": event["evidence_id"],
            }
        )
    for event in by_family.get("chart", []):
        if event["itemid_num"] in WEIGHT_ITEMIDS and event["value_num"] is not None:
            weight_rows.append((event["event_time"], event["itemid_num"], event["value_num"]))
            continue
        concept = chart_map.get(event["itemid_num"]) if event["itemid_num"] is not None else None
        if concept is None or event["value_num"] is None:
            continue
        availability = event["availability_time"]
        chart_events.append(
            {
                "concept": concept,
                "itemid": event["itemid_num"]
                if event["itemid_num"] is not None
                else event["itemid"],
                "valuenum": event["value_num"],
                "unit": event["unit"],
                "charttime": _ts(event["event_time"]),
                "storetime": (
                    _ts(availability)
                    if availability > event["event_time"]
                    else _ts(event["event_time"])
                ),
                "evidence_id": event["evidence_id"],
            }
        )
    for event in by_family.get("output", []):
        is_urine = (
            event["itemid_num"] in im.OUTPUT_URINE
            if event["itemid_num"] is not None
            else False
        )
        if is_urine and event["value_num"] is not None:
            availability = event["availability_time"]
            chart_events.append(
                {
                    "concept": c.URINE_OUTPUT,
                    "itemid": event["itemid_num"]
                    if event["itemid_num"] is not None
                    else event["itemid"],
                    "valuenum": event["value_num"],
                    "unit": "mL",
                    "charttime": _ts(event["event_time"]),
                    "storetime": (
                        _ts(availability)
                        if availability > event["event_time"]
                        else _ts(event["event_time"])
                    ),
                    "evidence_id": event["evidence_id"],
                }
            )
    for event in by_family.get("input", []):
        if event["itemid_num"] is not None and event["itemid_num"] in im.INPUT_VASOPRESSORS:
            pressor_rows.append(
                (event["event_time"], event, im.INPUT_VASOPRESSORS[event["itemid_num"]])
            )
    for event in by_family.get("diagnosis", []):
        diagnoses.append(
            {
                "icd_code": event["itemid"],
                "long_title": event["value_raw"] or "",
                "evidence_id": event["evidence_id"],
            }
        )
    # Pressor conversion runs after the full event scan so weight resolution
    # sees every charted weight regardless of index row order (same
    # availability-time rule as the source path).
    for event_time, event, agent in pressor_rows:
        weight = latest_weight_before(weight_rows=weight_rows, as_of=event_time)
        conv = convert_pressor_dose(
            rate=event["value_num"],
            rate_uom=event["unit"],
            weight_kg=weight.weight_kg,
            weight_available=weight.status == "resolved",
            weight_evidence_id=weight.evidence_id,
            evidence_id=event["evidence_id"],
            agent=agent,
        )
        chart_events.append(
            {
                "concept": c.VASOPRESSOR,
                "itemid": event["itemid"],
                "valuenum": conv.dose_ug_kg_min if conv.known else None,
                "unit": "mcg/kg/min" if conv.known else (event["unit"] or "unknown"),
                "charttime": _ts(event_time),
                "storetime": (
                    _ts(event["availability_time"])
                    if event["availability_time"] > event_time
                    else _ts(event_time)
                ),
                "evidence_id": event["evidence_id"],
                "display": agent,
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
    return _emit_indexed_stay(
        stay_meta=stay_row,
        lab_events=downsample_hourly(lab_events),
        chart_events=downsample_hourly(chart_events),
        diagnoses=diagnoses,
        evidence_prefix="mimic",
    )


def eicu_stays_from_index(index_dir: Path, stay_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Reconstruct demo-schema stays from index rows, reusing the eICU adapter.

    Index rows carry the full source row in ``extra_json``, so the Phase-B
    conversion (`convert_eicu_rows`) runs unchanged over reconstructed rows.
    """
    from ingestion.adapters.eicu.convert import convert_eicu_rows

    stays = {str(s["stay_id"]): s for s in load_stays(index_dir)}
    wanted = set(stay_ids)
    patients = [
        row["extra_json"] if isinstance(row.get("extra_json"), dict) else {}
        for sid, row in stays.items()
        if sid in wanted
    ]

    def _rows(family: str):
        for sid in sorted(wanted, key=lambda x: (int(x) if x.isdigit() else 1 << 63, x)):
            for event in load_stay_events(index_dir, sid):
                if event["event_family"] == family and isinstance(event.get("extra_json"), dict):
                    yield event["extra_json"]

    converted = convert_eicu_rows(
        patients=patients,
        labs=_rows("lab"),
        vital_periodic=_rows("vital_periodic"),
        vital_aperiodic=_rows("vital_aperiodic"),
        nurse_charting=_rows("nurse_charting"),
        respiratory_charting=_rows("respiratory_charting"),
        intake_output=_rows("intake_output"),
        infusion_drug=_rows("infusion_drug"),
        physical_exam=_rows("physical_exam"),
        limit=None,
    )
    return {str(stay["stay_id"]): stay for stay in converted["stays"]}


def select_stay_ids(
    index_dir: Path,
    *,
    stay_ids: list[str] | None = None,
    limit: int | None = None,
    apply_protocol_cohort: bool = False,
    seed: int = 42,
) -> list[str]:
    """Resolve the stay list. ``limit=0``/None → all stays (full run)."""
    from ingestion.completeness import (
        filter_eicu_protocol_cohort,
        filter_mimic_protocol_cohort,
        seeded_sample,
    )

    all_stays = load_stays(index_dir)
    if apply_protocol_cohort:
        meta = load_index_meta(index_dir)
        if meta["config"]["dataset"] == "mimic":
            icustays = [
                s["extra_json"] if isinstance(s.get("extra_json"), dict) else {}
                for s in all_stays
            ]
            patients_rows = _load_mimic_patients_rows(index_dir)
            cohort = filter_mimic_protocol_cohort(icustays=icustays, patients=patients_rows)
        else:
            patient_rows = [
                s["extra_json"] if isinstance(s.get("extra_json"), dict) else {}
                for s in all_stays
            ]
            cohort = filter_eicu_protocol_cohort(patient_rows)
        cohort_ids = [str(r["stay_id"]) for r in cohort]
        by_id = {str(s["stay_id"]): s for s in all_stays}
        cohort_ids = [sid for sid in cohort_ids if sid in by_id]
        if limit and limit > 0:
            cohort_ids = seeded_sample(cohort_ids, limit, seed=seed)
        return cohort_ids
    if stay_ids:
        return list(stay_ids)
    ordered = [str(s["stay_id"]) for s in all_stays]
    if limit and limit > 0:
        return ordered[:limit]
    return ordered


def _load_mimic_patients_rows(index_dir: Path) -> list[dict[str, str]]:
    """MIMIC patients rows (subject_id/anchor_age) stored as a cohort table."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise IndexError("pyarrow is required; install with pip install -e '.[study]'") from exc

    path = index_dir / "patients.parquet"
    if not path.is_file():
        return []
    return [
        {"subject_id": str(r["subject_id"]), "anchor_age": str(r["anchor_age"])}
        for r in pq.read_table(path).to_pylist()
    ]


def replay_indexed_stays(
    *,
    index_dir: Path,
    stay_ids: list[str] | None = None,
    limit: int | None = None,
    apply_protocol_cohort: bool = False,
    seed: int = 42,
    score_every_event: bool = False,
) -> dict[str, Any]:
    """Replay indexed stays through the leakage-safe harness.

    ``limit=0`` (or None) replays every stay — the full credentialed run.
    """
    meta = load_index_meta(index_dir)
    dataset = meta["config"]["dataset"]
    selected = select_stay_ids(
        index_dir,
        stay_ids=stay_ids,
        limit=limit,
        apply_protocol_cohort=apply_protocol_cohort,
        seed=seed,
    )
    stays = {str(s["stay_id"]): s for s in load_stays(index_dir)}
    missing = [sid for sid in selected if sid not in stays]
    if missing:
        raise IndexError(f"stay ids missing from index: {missing[:10]}")

    family_counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    if dataset == "eicu":
        stay_map = eicu_stays_from_index(index_dir, selected)
    else:
        stay_map = {}
    for sid in selected:
        events = load_stay_events(index_dir, sid)
        for event in events:
            family_counts[event["event_family"]] += 1
        if dataset == "mimic":
            stay = mimic_stay_from_index(index_dir, stays[sid])
        else:
            stay = stay_map[sid]
        result = replay_stay(stay, check_leakage=True, score_every_event=score_every_event)
        public = result_to_public_dict(result)
        results.append(public)
        errors.extend(f"{sid}: {err}" for err in result.errors)

    return {
        "replay_version": REPLAY_VERSION,
        "dataset": meta["dataset"]["name"],
        "dataset_version": meta["dataset"]["version"],
        "index_dir": str(index_dir),
        "index_hash": meta["index_hash"],
        "selection": {
            "mode": (
                "stay_ids"
                if stay_ids
                else (
                    "protocol_cohort"
                    if apply_protocol_cohort
                    else ("bounded" if limit else "full")
                )
            ),
            "limit": limit,
            "seed": seed if apply_protocol_cohort else None,
            "stay_ids": selected,
        },
        "stays_replayed": len(results),
        "event_counts": dict(family_counts),
        "errors": errors,
        "missingness": sofa_component_missing_rates(results),
        "stays": results,
    }


def _index_storage_bytes(index_dir: Path) -> int:
    total = 0
    for path in index_dir.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def build_and_write_manifest(
    *,
    index_dir: Path,
    report: dict[str, Any],
    runtime_s: float,
    peak_rss_bytes: int,
    cli_argv: list[str],
    manifest_out: Path | None = None,
) -> dict[str, Any]:
    """Attach a reproducible run manifest to an indexed replay."""
    from eval.mimic_study.manifest import build_run_manifest

    meta = load_index_meta(index_dir)
    manifest = build_run_manifest(
        dataset=meta["config"]["dataset"],
        index_dir=index_dir,
        index_meta=meta,
        cohort={
            "selection": report["selection"],
            "stays_replayed": report["stays_replayed"],
        },
        counts={
            "events_replayed": sum(report["event_counts"].values()),
            "events_by_family": report["event_counts"],
            "errors": len(report["errors"]),
        },
        timestamp_failures={
            src: info.get("timestamp_failures") or 0
            for src, info in (meta.get("source_files") or {}).items()
        },
        missingness=report["missingness"],
        runtime_s=runtime_s,
        peak_rss_bytes=peak_rss_bytes,
        storage_bytes=_index_storage_bytes(index_dir),
        cli_argv=cli_argv,
    )
    out = manifest_out or (index_dir / "runs" / f"run-{manifest['run_id']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest["manifest_path"] = str(out)
    return manifest


def run_with_manifest(
    *,
    index_dir: Path,
    stay_ids: list[str] | None = None,
    limit: int | None = None,
    apply_protocol_cohort: bool = False,
    seed: int = 42,
    score_every_event: bool = False,
    manifest_out: Path | None = None,
    cli_argv: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    start = time.perf_counter()
    report = replay_indexed_stays(
        index_dir=index_dir,
        stay_ids=stay_ids,
        limit=limit,
        apply_protocol_cohort=apply_protocol_cohort,
        seed=seed,
        score_every_event=score_every_event,
    )
    runtime_s = time.perf_counter() - start
    peak_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # ru_maxrss is KiB on Linux, bytes on macOS.
    if sys.platform.startswith("linux"):
        peak_rss *= 1024
    manifest = build_and_write_manifest(
        index_dir=index_dir,
        report=report,
        runtime_s=runtime_s,
        peak_rss_bytes=peak_rss,
        cli_argv=cli_argv or sys.argv,
        manifest_out=manifest_out,
    )
    return report, manifest


def benchmark(
    *,
    source_root: Path,
    index_dir: Path,
    dataset: str = "mimic",
    limit: int = 20,
) -> dict[str, Any]:
    """Compressed-source scan vs indexed replay on a bounded cohort."""
    import tracemalloc

    selected = select_stay_ids(index_dir, limit=limit)

    source_sizes = _source_table_sizes(source_root, dataset)
    index_bytes = _index_storage_bytes(index_dir)

    tracemalloc.start()
    t0 = time.perf_counter()
    if dataset == "mimic":
        from ingestion.adapters.mimic.to_demo_schema import convert_mimic_demo

        converted = convert_mimic_demo(
            source_root,
            stays=[
                s["extra_json"] if isinstance(s.get("extra_json"), dict) else {}
                for s in load_stays(index_dir)
                if str(s["stay_id"]) in set(selected)
            ],
        )
        source_stays = converted["stays"]
    else:
        source_stays = eicu_source_stays_for_benchmark(source_root, selected)
    source_scan_s = time.perf_counter() - t0
    _, source_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    source_results = [
        result_to_public_dict(replay_stay(stay, score_every_event=False)) for stay in source_stays
    ]

    tracemalloc.start()
    t0 = time.perf_counter()
    indexed = replay_indexed_stays(index_dir=index_dir, stay_ids=selected, score_every_event=False)
    index_replay_s = time.perf_counter() - t0
    _, index_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Content equivalence compares the same artifact on both paths: the
    # demo-schema stay (labs/charts), not the replay result dicts.
    if dataset == "mimic":
        stays_by_id = {str(s["stay_id"]): s for s in load_stays(index_dir)}
        indexed_stays = [
            mimic_stay_from_index(index_dir, stays_by_id[sid]) for sid in selected
        ]
    else:
        indexed_stays = list(eicu_stays_from_index(index_dir, selected).values())

    def _hash_results(
        results: list[dict[str, Any]], *, semantic: bool
    ) -> str:
        payload: list[Any] = []
        for r in results:
            snap = r.get("final_snapshot") or {}
            if semantic:
                payload.append(
                    {
                        "score": snap.get("score"),
                        "completeness": snap.get("completeness"),
                        "missing_components": sorted(snap.get("missing_components") or []),
                    }
                )
            else:
                payload.append(snap)
        encoded = json.dumps(payload, sort_keys=True, default=str)
        return sha256_hex(encoded.encode("utf-8"))

    def _content_fingerprint(stays: list[dict[str, Any]]) -> dict[str, list]:
        out: dict[str, list] = {}
        for stay in stays:
            items = []
            for lab in stay.get("labs") or []:
                items.append(
                    (
                        "lab",
                        lab.get("code"),
                        lab.get("itemid"),
                        lab.get("valuenum"),
                        lab.get("unit"),
                        lab.get("charttime"),
                    )
                )
            for chart in stay.get("charts") or []:
                items.append(
                    (
                        "chart",
                        chart.get("code"),
                        chart.get("itemid"),
                        chart.get("valuenum"),
                        chart.get("unit"),
                        chart.get("charttime"),
                    )
                )
            out[str(stay.get("stay_id"))] = sorted(items, key=lambda x: json.dumps(x, default=str))
        return out

    availability_shifted = 0
    for stay_row in load_stays(index_dir):
        if str(stay_row["stay_id"]) not in set(selected):
            continue
        events = load_stay_events(index_dir, str(stay_row["stay_id"]))
        if any(
            e["event_family"] == "lab" and e["availability_time"] > e["event_time"]
            for e in events
        ):
            availability_shifted += 1
    content_equivalent = _content_fingerprint(source_stays) == _content_fingerprint(
        indexed_stays
    )
    return {
        "benchmark_version": REPLAY_VERSION,
        "dataset": dataset,
        "cohort_stays": len(selected),
        "storage": {
            "source_tables_bytes": source_sizes,
            "source_tables_total_bytes": sum(source_sizes.values()),
            "index_bytes": index_bytes,
        },
        "runtime_s": {
            "source_scan_and_convert": round(source_scan_s, 3),
            "indexed_load_and_replay": round(index_replay_s, 3),
            "ratio": (
                round(source_scan_s / index_replay_s, 2) if index_replay_s > 0 else None
            ),
        },
        "memory": {
            "source_scan_peak_bytes": source_peak,
            "indexed_peak_bytes": index_peak,
        },
        "equivalence": {
            "event_content_equivalent": bool(content_equivalent),
            "final_snapshots_identical": bool(
                _hash_results(source_results, semantic=False)
                == _hash_results(indexed["stays"], semantic=False)
            ),
            "final_snapshots_score_equivalent": bool(
                _hash_results(source_results, semantic=True)
                == _hash_results(indexed["stays"], semantic=True)
            ),
            "stays_with_lab_availability_shift": availability_shifted,
            "note": (
                "The indexed path honors true lab storetime (availability-time "
                "replay), so snapshot clocks may differ from the demo-schema path "
                "that uses charttime as availability; event content is unchanged."
            ),
        },
    }


def _source_table_sizes(source_root: Path, dataset: str) -> dict[str, int]:
    from eval.mimic_study.indexing import _family_specs

    sizes: dict[str, int] = {}
    for spec in _family_specs(dataset, "mapped"):
        path = source_root / spec.source_file
        if path.is_file():
            sizes[spec.source_file] = path.stat().st_size
    return sizes


def eicu_source_stays_for_benchmark(
    source_root: Path, stay_ids: list[str]
) -> list[dict[str, Any]]:
    """eICU source-scan baseline for the benchmark (same adapter path)."""
    from ingestion.adapters.eicu.convert import _iter_csv_gz

    wanted = set(stay_ids)
    patients = [
        row
        for row in _iter_csv_gz(source_root / "patient.csv.gz")
        if (row.get("patientunitstayid") or "").strip() in wanted
    ]

    def _rows(table: str):
        for row in _iter_csv_gz(source_root / table):
            if (row.get("patientunitstayid") or "").strip() in wanted:
                yield row

    from ingestion.adapters.eicu.convert import convert_eicu_rows

    return convert_eicu_rows(
        patients=patients,
        labs=_rows("lab.csv.gz"),
        vital_periodic=_rows("vitalPeriodic.csv.gz"),
        vital_aperiodic=_rows("vitalAperiodic.csv.gz"),
        nurse_charting=_rows("nurseCharting.csv.gz"),
        respiratory_charting=_rows("respiratoryCharting.csv.gz"),
        intake_output=_rows("intakeOutput.csv.gz"),
        infusion_drug=_rows("infusionDrug.csv.gz"),
        physical_exam=_rows("physicalExam.csv.gz"),
        limit=None,
    )["stays"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Availability-time replay over the MIMIC/eICU stay index (Phase C)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="bounded or full indexed replay + run manifest")
    p_run.add_argument("--dataset", choices=("mimic", "eicu"), default="mimic")
    p_run.add_argument("--index-dir", type=Path, default=None)
    p_run.add_argument("--limit", type=int, default=50, help="0 = all stays")
    p_run.add_argument("--stay-ids", nargs="*", default=None)
    p_run.add_argument("--protocol-cohort", action="store_true")
    p_run.add_argument("--seed", type=int, default=42)
    p_run.add_argument("--score-every-event", action="store_true")
    p_run.add_argument("--manifest-out", type=Path, default=None)
    p_run.add_argument("--json-out", type=Path, default=None)

    p_bench = sub.add_parser("benchmark", help="source scan vs indexed replay benchmark")
    p_bench.add_argument("--dataset", choices=("mimic", "eicu"), default="mimic")
    p_bench.add_argument("--source", type=Path, default=None)
    p_bench.add_argument("--index-dir", type=Path, default=None)
    p_bench.add_argument("--limit", type=int, default=20)
    p_bench.add_argument("--json-out", type=Path, default=None)

    args = parser.parse_args(argv)
    from eval.mimic_study.indexing import default_index_dir

    if args.cmd == "run":
        index_dir = args.index_dir or default_index_dir(args.dataset)
        limit = None if args.limit == 0 else args.limit
        report, manifest = run_with_manifest(
            index_dir=index_dir,
            stay_ids=args.stay_ids,
            limit=limit,
            apply_protocol_cohort=args.protocol_cohort,
            seed=args.seed,
            score_every_event=args.score_every_event,
            manifest_out=args.manifest_out,
            cli_argv=sys.argv,
        )
        summary = {
            "dataset": report["dataset"],
            "stays_replayed": report["stays_replayed"],
            "event_counts": report["event_counts"],
            "missingness": report["missingness"],
            "manifest_path": manifest["manifest_path"],
            "run_id": manifest["run_id"],
            "content_hash": manifest["content_hash"],
        }
        print(json.dumps(summary, indent=2))
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps({"report": report, "manifest": manifest}, indent=2, default=str)
            )
        return 0

    if args.cmd == "benchmark":
        index_dir = args.index_dir or default_index_dir(args.dataset)
        meta = load_index_meta(index_dir)
        source_root = args.source or Path(meta["source_root"])
        result = benchmark(
            source_root=source_root, index_dir=index_dir, dataset=args.dataset, limit=args.limit
        )
        print(json.dumps(result, indent=2))
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json.dumps(result, indent=2) + "\n")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
