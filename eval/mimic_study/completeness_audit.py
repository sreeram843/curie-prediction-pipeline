"""Phase A completeness audit for credentialed MIMIC-IV (CURIE-049 extension).

AUDIT-ONLY: outputs are written under ``data/audit/`` and are NOT frozen study
numbers. Freezing requires the Phase B/C integration gate (see
``docs/superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md``).

What this does (all read-only, one pass per source table):

1. Cohort-filtered streaming statistics for every SOFA component: row counts,
   stay coverage, first-ICU-day coverage, and event-time distribution (hour of
   stay). FiO2 / PaO2 / SpO2 / creatinine / urine / GCS / platelets / bilirubin /
   MAP / pressors are measured separately.
2. Pressor dose classification under the B1 unit policy: known vs unknown dose,
   unit-conversion success vs unsupported, weight availability for weight-needing
   units.
3. Source/index reconciliation: the loader indexers are re-run for a bounded stay
   sample and compared row-for-row against an independent direct scan.
4. Bounded sharded replay (seeded, default 8000 stays) reporting complete vs
   partial SOFA coverage and missing components from the harness snapshots.
5. Runtime and peak RSS for the streaming passes.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import resource
import shutil
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.loader import iter_csv_gz
from ingestion.adapters.mimic.paths import require_mimic_dir
from ingestion.adapters.mimic.vasopressors import convert_pressor_dose
from ingestion.completeness import DEFAULT_SAMPLE_SEED

LAB_GROUPS: dict[str, set[int]] = {
    "creatinine": set(im.LAB_CREATININE),
    "platelets": set(im.LAB_PLATELETS),
    "bilirubin_total": set(im.LAB_BILIRUBIN_TOTAL),
    "pao2": set(im.LAB_PAO2),
}
CHART_GROUPS: dict[str, set[int]] = {
    "map": set(im.CHART_MAP),
    "spo2": set(im.CHART_SPO2),
    "fio2": set(im.CHART_FIO2),
    "gcs_eye": set(im.CHART_GCS_EYE),
    "gcs_verbal": set(im.CHART_GCS_VERBAL),
    "gcs_motor": set(im.CHART_GCS_MOTOR),
    "creatinine": set(im.CHART_CREATININE),
    "bilirubin_total": set(im.CHART_BILIRUBIN),
    "platelets": set(im.CHART_PLATELETS),
}
WEIGHT_ITEMIDS = {224639, 226512, 226531}


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
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class StayStats:
    __slots__ = (
        "intime",
        "counts",
        "first_day",
        "row_ts_fail",
        "row_val_fail",
        "hour_hist",
    )

    def __init__(self, intime: datetime | None) -> None:
        self.intime = intime
        self.counts: Counter[str] = Counter()
        self.first_day: Counter[str] = Counter()
        self.row_ts_fail = 0
        self.row_val_fail = 0
        self.hour_hist: Counter[int] = Counter()


def _note(stats: StayStats, group: str, t: datetime | None, hour: int | None) -> None:
    stats.counts[group] += 1
    if hour is not None:
        stats.hour_hist[hour] += 1
    if stats.intime is not None and t is not None:
        if 0 <= (t - stats.intime).total_seconds() < 24 * 3600:
            stats.first_day[group] += 1


def stream_stats(
    root: Path,
    stays: list[dict[str, Any]],
    *,
    limit_stays: int | None = None,
    limit_rows: int | None = None,
) -> dict[str, Any]:
    stay_ids = {s["stay_id"] for s in stays}
    subject_to_stays: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in stays:
        subject_to_stays[s["subject_id"]].append(s)
    subject_ids = set(subject_to_stays)

    def stay_for(sid: str, hadm: str | None) -> dict[str, Any] | None:
        for s in subject_to_stays.get(sid, []):
            if not hadm or s.get("hadm_id") in {"", hadm}:
                return s
        return None

    stats: dict[str, StayStats] = {}
    for s in stays:
        stats[s["stay_id"]] = StayStats(_parse_ts(s.get("intime")))
    if limit_stays is not None:
        kept_ids = set(list(stay_ids)[:limit_stays])
    else:
        kept_ids = stay_ids

    t0 = time.time()

    # --- hosp/labevents (subject/hadm keyed) ---
    lab_path = root / "hosp" / "labevents.csv.gz"
    wanted_lab = {str(i) for g in LAB_GROUPS.values() for i in g}
    lab_seen = 0
    for row in iter_csv_gz(lab_path):
        lab_seen += 1
        if limit_rows is not None and lab_seen > limit_rows:
            break
        sid = row.get("subject_id") or ""
        if sid not in subject_ids:
            continue
        if row.get("itemid") not in wanted_lab:
            continue
        s = stay_for(sid, row.get("hadm_id"))
        if s is None or s["stay_id"] not in kept_ids:
            continue
        st = stats[s["stay_id"]]
        group = next(
            (g for g, ids in LAB_GROUPS.items() if int(row["itemid"]) in ids), None
        )
        if group is None:
            continue
        t = _parse_ts(row.get("charttime"))
        if t is None:
            st.row_ts_fail += 1
        if _to_float(row.get("valuenum")) is None:
            st.row_val_fail += 1
        hour = None
        if t is not None and st.intime is not None:
            hour = max(0, int((t - st.intime).total_seconds() // 3600))
        _note(st, group, t, hour)

    # --- icu/chartevents ---
    chart_path = root / "icu" / "chartevents.csv.gz"
    wanted_chart = {str(i) for g in CHART_GROUPS.values() for i in g} | {
        str(i) for i in WEIGHT_ITEMIDS
    }
    chart_seen = 0
    for row in iter_csv_gz(chart_path):
        chart_seen += 1
        if limit_rows is not None and chart_seen > limit_rows:
            break
        sid_stay = row.get("stay_id") or ""
        if sid_stay not in kept_ids:
            continue
        itemid = row.get("itemid")
        if itemid not in wanted_chart:
            continue
        st = stats[sid_stay]
        t = _parse_ts(row.get("charttime"))
        if t is None:
            st.row_ts_fail += 1
        if _to_float(row.get("valuenum")) is None:
            st.row_val_fail += 1
        hour = None
        if t is not None and st.intime is not None:
            hour = max(0, int((t - st.intime).total_seconds() // 3600))
        iid = int(itemid)
        if iid in WEIGHT_ITEMIDS:
            _note(st, "weight", t, hour)
            continue
        for g, ids in CHART_GROUPS.items():
            if iid in ids:
                _note(st, g, t, hour)
                break

    # --- icu/outputevents (urine) ---
    out_path = root / "icu" / "outputevents.csv.gz"
    wanted_urine = {str(i) for i in im.OUTPUT_URINE}
    out_seen = 0
    for row in iter_csv_gz(out_path):
        out_seen += 1
        if limit_rows is not None and out_seen > limit_rows:
            break
        sid_stay = row.get("stay_id") or ""
        if sid_stay not in kept_ids:
            continue
        if row.get("itemid") not in wanted_urine:
            continue
        st = stats[sid_stay]
        t = _parse_ts(row.get("charttime"))
        if _to_float(row.get("value")) is None:
            st.row_val_fail += 1
        hour = None
        if t is not None and st.intime is not None:
            hour = max(0, int((t - st.intime).total_seconds() // 3600))
        _note(st, "urine_output", t, hour)

    # --- icu/inputevents (pressors) + B1 dose classification ---
    in_path = root / "icu" / "inputevents.csv.gz"
    wanted_pressor = {str(i) for i in im.INPUT_VASOPRESSORS}
    dose_class: Counter[str] = Counter()
    unit_class: Counter[str] = Counter()
    in_seen = 0
    for row in iter_csv_gz(in_path):
        in_seen += 1
        if limit_rows is not None and in_seen > limit_rows:
            break
        sid_stay = row.get("stay_id") or ""
        if sid_stay not in kept_ids:
            continue
        if row.get("itemid") not in wanted_pressor:
            continue
        st = stats[sid_stay]
        t = _parse_ts(row.get("starttime"))
        hour = None
        if t is not None and st.intime is not None:
            hour = max(0, int((t - st.intime).total_seconds() // 3600))
        _note(st, "pressor", t, hour)
        conv = convert_pressor_dose(
            rate=_to_float(row.get("rate")),
            rate_uom=row.get("rateuom"),
            # MIMIC inputevents has no patientweight column; weight resolution
            # requires chartevents (see ingestion.adapters.mimic.vasopressors).
            # Phase C index wiring tracks raw units here; dose classification
            # of mcg/min|mg/min rows is reported as weight-unavailable.
            weight_kg=None,
            weight_available=False,
        )
        if conv.known:
            dose_class["known"] += 1
        else:
            dose_class["unknown"] += 1
        unit_class[conv.source_unit or "missing"] += 1
        dose_class[f"reason:{conv.reason}"] += 1

    wall = time.time() - t0
    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    # --- aggregate ---
    component_groups = {
        "respiration_fio2": ["fio2"],
        "respiration_pao2": ["pao2"],
        "respiration_spo2": ["spo2"],
        "renal_creatinine": ["creatinine"],
        "renal_urine_output": ["urine_output"],
        "cns_gcs": ["gcs_eye", "gcs_verbal", "gcs_motor"],
        "coagulation_platelets": ["platelets"],
        "liver_bilirubin": ["bilirubin_total"],
        "cardiovascular_map": ["map"],
        "cardiovascular_pressor": ["pressor"],
    }
    n_stays = len(kept_ids)
    components: dict[str, Any] = {}
    hour_hist_total: Counter[int] = Counter()
    for comp, groups in component_groups.items():
        n_covered = 0
        n_first_day = 0
        n_rows = 0
        for sid_stay in kept_ids:
            st = stats[sid_stay]
            any_row = any(st.counts[g] > 0 for g in groups)
            if any_row:
                n_covered += 1
            if any(st.first_day[g] > 0 for g in groups):
                n_first_day += 1
            n_rows += sum(st.counts[g] for g in groups)
        components[comp] = {
            "stays_with_observation": n_covered,
            "observation_rate": n_covered / n_stays if n_stays else 0.0,
            "stays_with_first_day_observation": n_first_day,
            "first_day_rate": n_first_day / n_stays if n_stays else 0.0,
            "rows": n_rows,
        }
    for sid_stay in kept_ids:
        hour_hist_total.update(stats[sid_stay].hour_hist)

    gcs_complete = 0
    for sid_stay in kept_ids:
        st = stats[sid_stay]
        if (
            st.counts["gcs_eye"] > 0
            and st.counts["gcs_verbal"] > 0
            and st.counts["gcs_motor"] > 0
        ):
            gcs_complete += 1

    ts_fail = sum(stats[s].row_ts_fail for s in kept_ids)
    val_fail = sum(stats[s].row_val_fail for s in kept_ids)

    return {
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "stays_in_audit": n_stays,
        "components": components,
        "gcs_all_three_subscales_present_stays": gcs_complete,
        "pressor_dose": {
            "classification": dict(sorted(dose_class.items())),
            "source_units": dict(sorted(unit_class.items())),
        },
        "weight_observation_stays": sum(
            1 for s in kept_ids if stats[s].counts["weight"] > 0
        ),
        "row_quality": {
            "timestamp_parse_failures": ts_fail,
            "valuenum_parse_failures": val_fail,
        },
        "event_time_distribution_hours_since_intime": {
            str(k): v for k, v in sorted(hour_hist_total.items())[:24]
        },
        "runtime": {"stream_seconds": round(wall, 2), "peak_rss_kb": peak_rss_kb},
    }


def reconcile_loader_vs_direct(
    root: Path, stays: list[dict[str, Any]], *, n_stays: int = 25
) -> dict[str, Any]:
    """Row-for-row reconciliation between the loader indexers and an independent scan.

    Row identity is (itemid, event time, numeric value). The loader converts
    values to float, so both sides normalize through float to compare content,
    not source-string formatting.
    """
    from ingestion.adapters.mimic.loader import (
        index_chartevents,
        index_labevents,
    )

    sample = stays[:n_stays]
    stay_ids = {s["stay_id"] for s in sample}
    subject_ids = {s["subject_id"] for s in sample}
    chart_wanted = set().union(*CHART_GROUPS.values())
    lab_wanted = set().union(*LAB_GROUPS.values())

    def _direct(
        path: Path,
        *,
        key: str,
        key_set: set[str],
        wanted: set[int],
        hadm_filter: set[str] | None = None,
    ) -> set[tuple]:
        wanted_s = {str(i) for i in wanted}
        out: set[tuple] = set()
        for row in iter_csv_gz(path):
            if row.get(key) not in key_set:
                continue
            if hadm_filter is not None and row.get("hadm_id") not in hadm_filter:
                continue
            if row.get("itemid") not in wanted_s:
                continue
            val = _to_float(row.get("valuenum"))
            if val is None:
                continue
            out.add((int(row["itemid"]), row.get("charttime") or "", val))
        return out

    hadm_ids = {s.get("hadm_id") or "" for s in sample} | {""}
    direct_chart = _direct(
        root / "icu" / "chartevents.csv.gz",
        key="stay_id",
        key_set=stay_ids,
        wanted=chart_wanted,
    )
    direct_lab = _direct(
        root / "hosp" / "labevents.csv.gz",
        key="subject_id",
        key_set=subject_ids,
        wanted=lab_wanted,
        hadm_filter=hadm_ids,
    )

    loader_chart = index_chartevents(root, stay_ids=stay_ids, itemids=chart_wanted)
    loader_chart_set = {
        (r["itemid"], r["charttime"], r["valuenum"])
        for rows in loader_chart.values()
        for r in rows
    }
    loader_lab = index_labevents(root, subject_ids=subject_ids, itemids=lab_wanted)
    loader_lab_set = {
        (r["itemid"], r["charttime"], r["valuenum"])
        for rows in loader_lab.values()
        for r in rows
        if r.get("hadm_id") in hadm_ids
    }

    def _compare(direct: set[tuple], loader: set[tuple]) -> dict[str, Any]:
        return {
            "direct_rows": len(direct),
            "loader_rows": len(loader),
            "missing_from_loader": len(direct - loader),
            "extra_in_loader": len(loader - direct),
            "match": direct == loader,
        }

    return {
        "sample_stays": n_stays,
        "row_identity": "(itemid, event_time, numeric_value)",
        "tables": {
            "chartevents": _compare(direct_chart, loader_chart_set),
            "labevents": _compare(direct_lab, loader_lab_set),
        },
    }


def _sharded_replay(
    root: Path,
    stays: list[dict[str, Any]],
    *,
    limit: int,
    seed: int,
    batch_size: int,
) -> dict[str, Any]:
    """One-pass sharding of source rows for sampled stays, then batched replay."""
    from eval.mimic_harness.replay import replay_stay, result_to_public_dict
    from eval.sofa.scoring import SOFA_COMPONENTS
    from ingestion.adapters.mimic.to_demo_schema import convert_mimic_demo
    from ingestion.completeness import seeded_sample

    sample = seeded_sample(stays, limit, seed=seed)
    stay_ids = {s["stay_id"] for s in sample}
    subject_ids = {s["subject_id"] for s in sample}
    batches = [sample[i : i + batch_size] for i in range(0, len(sample), batch_size)]

    tmp = Path(tempfile.mkdtemp(prefix="curie-mimic-shards-"))
    shard_root = tmp / "shard"
    try:
        # copy small icustays + admissions so convert_mimic_demo(stays=...) works
        (shard_root / "icu").mkdir(parents=True)
        (shard_root / "hosp").mkdir(parents=True)
        _shard_pass(
            root / "icu" / "chartevents.csv.gz",
            shard_root / "icu" / "chartevents.csv.gz",
            "stay_id",
            stay_ids,
            {str(i) for g in CHART_GROUPS.values() for i in g}
            | {str(i) for i in WEIGHT_ITEMIDS},
        )
        _shard_pass(
            root / "icu" / "inputevents.csv.gz",
            shard_root / "icu" / "inputevents.csv.gz",
            "stay_id",
            stay_ids,
            {str(i) for i in im.INPUT_VASOPRESSORS},
        )
        _shard_pass(
            root / "icu" / "outputevents.csv.gz",
            shard_root / "icu" / "outputevents.csv.gz",
            "stay_id",
            stay_ids,
            {str(i) for i in im.OUTPUT_URINE},
        )
        _shard_pass(
            root / "hosp" / "labevents.csv.gz",
            shard_root / "hosp" / "labevents.csv.gz",
            "subject_id",
            subject_ids,
            {str(i) for g in LAB_GROUPS.values() for i in g},
        )

        missing: Counter[str] = Counter()
        completeness: Counter[str] = Counter()
        n_scored = 0
        for bi, batch in enumerate(batches):
            print(f"  replay batch {bi + 1}/{len(batches)}", flush=True)
            converted = convert_mimic_demo(shard_root, stays=batch)
            for stay in converted["stays"]:
                row = result_to_public_dict(replay_stay(stay, score_every_event=False))
                snap = row.get("final_snapshot") or {}
                completeness[str(snap.get("completeness") or "unknown")] += 1
                for component in snap.get("missing_components") or []:
                    missing[str(component)] += 1
                n_scored += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    rates = {
        name.value: {
            "missing_stays": int(missing.get(name.value, 0)),
            "missing_rate": (missing.get(name.value, 0) / n_scored) if n_scored else 0.0,
        }
        for name in SOFA_COMPONENTS
    }
    return {
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "sample": {"limit": limit, "seed": seed, "scored_stays": n_scored},
        "completeness": dict(completeness),
        "components": rates,
    }


def _shard_pass(
    src: Path,
    dst: Path,
    key: str,
    wanted_keys: set[str],
    wanted_itemids: set[str],
) -> None:
    if not src.is_file():
        return
    with gzip.open(src, "rt", newline="") as fh_in, gzip.open(dst, "wt", newline="") as fh_out:
        reader = csv.DictReader(fh_in)
        writer = csv.DictWriter(fh_out, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row.get(key) not in wanted_keys:
                continue
            if row.get("itemid") not in wanted_itemids:
                continue
            writer.writerow(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIMIC completeness audit (not frozen)")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--limit-stays", type=int, default=None)
    parser.add_argument("--limit-rows", type=int, default=None)
    parser.add_argument("--sample-replay", type=int, default=8000)
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--skip-reconcile", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args(argv)

    root = require_mimic_dir()
    from eval.mimic_study.cohort_flow import apply_cohort

    print(f"applying cohort on {root}", flush=True)
    cohort = apply_cohort(root)
    stays = cohort["stays"]
    print(f"cohort stays: {len(stays)}", flush=True)

    print("streaming completeness stats", flush=True)
    out = stream_stats(root, stays, limit_stays=args.limit_stays, limit_rows=args.limit_rows)
    out["cohort"] = {
        "protocol_id": cohort["protocol_id"],
        "final_cohort_stays": cohort["cohort_flow"]["final_cohort_stays"],
        "audit_stays": out["stays_in_audit"],
        "split_status": cohort["splits"]["status"],
        "split_finding": cohort["splits"]["finding"],
    }
    out["row_scan_bound"] = args.limit_rows
    out["reconciliation"] = (
        None
        if args.skip_reconcile
        else reconcile_loader_vs_direct(root, stays)
    )

    if not args.no_replay:
        print(f"sharded replay sample (limit={args.sample_replay})", flush=True)
        out["sample_replay"] = _sharded_replay(
            root,
            stays,
            limit=args.sample_replay,
            seed=DEFAULT_SAMPLE_SEED,
            batch_size=args.batch_size,
        )
    else:
        out["sample_replay"] = None

    text = json.dumps(out, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n")
        print(f"wrote {args.json_out}", flush=True)
    else:
        print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
