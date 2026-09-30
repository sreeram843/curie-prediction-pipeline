"""Freeze disclosure-safe aggregates for the JBHI manuscript.

Builds ``frozen/publication_aggregates.v1.json`` from:

* the pinned Parquet index (v2 cohort flow, cohort characteristics);
* the materialized Sepsis-3 label artifact (per-split prevalence);
* hash-recorded completeness audits (MIMIC cohort-wide + seeded 8,000-stay
  MIMIC and eICU-CRD samples);
* the locked-test replay rows of the frozen operating point (lead-time
  distribution, lead-gated sensitivity, ICD label-sensitivity, subgroups);
* ``study_manifest.v3.json`` (ablations, copied verbatim).

Every cell is an aggregate. Cells describing fewer than ``MIN_CELL`` stays are
suppressed per the PhysioNet small-cell convention. The lead-time and ICD
analyses were specified after the locked test evaluation; they are reported as
post hoc secondary analyses and were never used for operating-point selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import stable_report_hash
from eval.mimic_study.bootstrap import bootstrap_percentile_ci
from eval.mimic_study.icd_sepsis import DEFAULT_PIN as ICD_PIN_PATH
from eval.mimic_study.protocol import load_protocol, split_for_anchor_year_group

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
OUTPUT_PATH = FROZEN_DIR / "publication_aggregates.v1.json"
MANIFEST_PATH = FROZEN_DIR / "study_manifest.v3.json"
OPERATING_POINT_PATH = FROZEN_DIR / "operating_point.v2.json"

MIN_CELL = 11
MIN_LOS_HOURS = 4.0
MIN_LEAD_HOURS = 2.0
BEFORE_HOURS = 12.0
AFTER_HOURS = 6.0
AGE_BANDS = ((18, 44), (45, 64), (65, 79), (80, 200))
LEAD_BIN_EDGES = (-6, -4, -2, 0, 2, 4, 6, 8, 10, 12)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None)
    text = str(raw).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def _extra(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("extra_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        return json.loads(raw)
    return {}


def _age_band(age: int | None) -> str | None:
    if age is None:
        return None
    for lo, hi in AGE_BANDS:
        if lo <= age <= hi:
            return f"{lo}+" if hi >= 200 else f"{lo}-{hi}"
    return None


def _quantiles(values: list[float]) -> dict[str, float] | None:
    if len(values) < MIN_CELL:
        return None
    ordered = sorted(values)
    q = statistics.quantiles(ordered, n=4, method="inclusive")
    return {"median": q[1], "q1": q[0], "q3": q[2]}


def _rate(num: int, den: int) -> float | None:
    if den < MIN_CELL:
        return None
    return num / den


# --------------------------------------------------------------------------- cohort


def build_cohort_flow(
    stays: list[dict[str, Any]],
    patients: dict[str, dict[str, Any]],
    *,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Stepwise denominators for the v2 selection used by the Stage B runner.

    Mirrors ``ingestion.completeness.filter_mimic_protocol_cohort``: adult,
    valid times, LOS >= 4 h, then the earliest *eligible* stay per admission,
    then anchor-year-group split assignment.
    """
    n_source = len(stays)
    adult: list[dict[str, Any]] = []
    for row in stays:
        age = patients.get(str(row.get("subject_id")), {}).get("anchor_age")
        if age is not None and age >= 18:
            adult.append(row)
    valid: list[tuple[dict[str, Any], datetime, datetime]] = []
    for row in adult:
        extra = _extra(row)
        intime = _parse_ts(extra.get("intime"))
        outtime = _parse_ts(extra.get("outtime"))
        if intime is None or outtime is None or outtime < intime:
            continue
        valid.append((row, intime, outtime))
    long_enough = [
        (row, intime)
        for row, intime, outtime in valid
        if (outtime - intime).total_seconds() / 3600.0 >= MIN_LOS_HOURS
    ]
    best: dict[str, tuple[dict[str, Any], datetime]] = {}
    for row, intime in long_enough:
        hadm = str(_extra(row).get("hadm_id") or row.get("hadm_id") or "")
        if not hadm:
            continue
        prev = best.get(hadm)
        if prev is None or intime < prev[1]:
            best[hadm] = (row, intime)
    cohort = [row for row, _ in best.values()]

    split_counts: Counter[str] = Counter()
    for row in cohort:
        group = patients.get(str(row.get("subject_id")), {}).get("anchor_year_group") or ""
        split_counts[split_for_anchor_year_group(group, protocol)] += 1

    # Legacy v1 audit rule: first ICU stay per admission chosen *before* the
    # valid-time and LOS filters, so a short or invalid first stay drops the admission.
    first_any: dict[str, tuple[dict[str, Any], datetime]] = {}
    for row in adult:
        extra = _extra(row)
        intime = _parse_ts(extra.get("intime"))
        if intime is None:
            continue
        hadm = str(extra.get("hadm_id") or row.get("hadm_id") or "")
        prev = first_any.get(hadm)
        if prev is None or intime < prev[1]:
            first_any[hadm] = (row, intime)
    v1_ids: set[str] = set()
    for row, intime in first_any.values():
        outtime = _parse_ts(_extra(row).get("outtime"))
        if outtime is None or outtime < intime:
            continue
        if (outtime - intime).total_seconds() / 3600.0 >= MIN_LOS_HOURS:
            v1_ids.add(str(row.get("stay_id")))
    cohort_ids = {str(r.get("stay_id")) for r in cohort}

    in_protocol = sum(split_counts[s] for s in ("development", "calibration", "test"))
    return {
        "selection": "v2: adult -> valid times -> LOS>=4h -> earliest eligible stay per hadm",
        "icustays_source": n_source,
        "excluded_age_under_18_or_unknown": n_source - len(adult),
        "excluded_invalid_intime_outtime": len(adult) - len(valid),
        "excluded_los_under_4h": len(valid) - len(long_enough),
        "excluded_later_stay_same_admission": len(long_enough) - len(cohort),
        "protocol_cohort_stays": len(cohort),
        "split_counts": {
            "development": split_counts["development"],
            "calibration": split_counts["calibration"],
            "test": split_counts["test"],
            "outside_protocol_anchor_groups": len(cohort) - in_protocol,
        },
        "study_stays_all_splits": in_protocol,
        "reconciliation_with_v1_audit": {
            "v1_rule": "first ICU stay per admission selected before the LOS/valid-time filters",
            "v1_rule_replicated_stays": len(v1_ids),
            "stays_in_both": len(cohort_ids & v1_ids),
            "stays_selected_only_under_v2_rule": len(cohort_ids - v1_ids),
            "stays_selected_only_under_v1_rule": len(v1_ids - cohort_ids),
            "explanation": (
                "v2 keeps a later ICU stay when the admission's first stay is invalid or "
                "shorter than 4 h; v1 dropped the whole admission."
            ),
        },
    }


def build_characteristics(
    stays: list[dict[str, Any]],
    patients: dict[str, dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    split_ids: dict[str, list[str]],
) -> dict[str, Any]:
    by_id = {str(r["stay_id"]): r for r in stays}
    out: dict[str, Any] = {}
    for split, ids in split_ids.items():
        ages: list[float] = []
        los: list[float] = []
        female = 0
        s3 = 0
        subjects: set[str] = set()
        for sid in ids:
            row = by_id[sid]
            patient = patients.get(str(row.get("subject_id")), {})
            subjects.add(str(row.get("subject_id")))
            if patient.get("anchor_age") is not None:
                ages.append(float(patient["anchor_age"]))
            if patient.get("gender") == "F":
                female += 1
            extra = _extra(row)
            intime, outtime = _parse_ts(extra.get("intime")), _parse_ts(extra.get("outtime"))
            if intime and outtime:
                los.append((outtime - intime).total_seconds() / 86400.0)
            if (labels.get(sid) or {}).get("sepsis3_onset") is not None:
                s3 += 1
        out[split] = {
            "stays": len(ids),
            "patients": len(subjects),
            "age_years": _quantiles(ages),
            "female": female,
            "female_rate": _rate(female, len(ids)),
            "icu_los_days": _quantiles(los),
            "sepsis3_positive": s3,
            "sepsis3_rate": _rate(s3, len(ids)),
        }
    return out


# --------------------------------------------------------------------------- test replay


def _lead_hours(row: dict[str, Any], field: str) -> float | None:
    """Lead of the earliest alert in [onset-12h, onset+6h]; None if none."""
    onset = _parse_ts((row.get("labels") or {}).get("sepsis3_onset"))
    if onset is None:
        return None
    best: float | None = None
    for raw in row.get(field) or []:
        t = _parse_ts(raw)
        if t is None:
            continue
        delta = (t - onset).total_seconds() / 3600.0
        if -BEFORE_HOURS <= delta <= AFTER_HOURS:
            lead = -delta
            if best is None or lead > best:
                best = lead
    return best


def stay_units(rows: list[dict[str, Any]], patients: dict[str, dict[str, Any]]) -> list[dict]:
    units = []
    for row in rows:
        patient = patients.get(str(row.get("subject_id")), {})
        units.append(
            {
                "s3": (row.get("labels") or {}).get("sepsis3_onset") is not None,
                "icd": bool(row.get("icd_sepsis_positive")),
                "lead_gov": _lead_hours(row, "governed_alert_times"),
                "lead_page": _lead_hours(row, "interruptive_alert_times"),
                "any_gov": bool(row.get("governed_alert_times")),
                "any_page": bool(row.get("interruptive_alert_times")),
                "pages": int(row.get("interruptive_alert_count") or 0),
                "days": float(row.get("patient_days") or 0.0),
                "sex": patient.get("gender"),
                "age_band": _age_band(patient.get("anchor_age")),
            }
        )
    return units


def _sens(units: list[dict], *, key: str, min_lead: float | None) -> float:
    pos = [u for u in units if u["s3"]]
    if not pos:
        raise ZeroDivisionError
    if min_lead is None:
        hit = sum(1 for u in pos if u[key] is not None)
    else:
        hit = sum(1 for u in pos if u[key] is not None and u[key] >= min_lead)
    return hit / len(pos)


def _icd_any(units: list[dict], *, key: str) -> float:
    pos = [u for u in units if u["icd"]]
    if not pos:
        raise ZeroDivisionError
    return sum(1 for u in pos if u[key]) / len(pos)


def _ci(stat, units: list[dict]) -> dict[str, float]:
    ci = bootstrap_percentile_ci(stat, units)
    return {k: ci[k] for k in ("point", "lo_2p5", "hi_97p5", "n_units", "n_replicates", "seed")}


def build_timing_and_labels(units: list[dict]) -> dict[str, Any]:
    pos = [u for u in units if u["s3"]]
    leads = [u["lead_gov"] for u in pos if u["lead_gov"] is not None]
    hist: list[dict[str, Any]] = []
    for lo, hi in zip(LEAD_BIN_EDGES[:-1], LEAD_BIN_EDGES[1:]):
        count = sum(1 for x in leads if lo <= x < hi or (hi == LEAD_BIN_EDGES[-1] and x == hi))
        hist.append({"lo": lo, "hi": hi, "count": count if count >= MIN_CELL else None})
    icd = [u for u in units if u["icd"]]
    overlap = [u for u in icd if u["s3"]]
    return {
        "role": "post_hoc_secondary",
        "note": (
            "Specified after the locked test evaluation; not used for operating-point "
            "selection. ICD codes are discharge diagnoses, not onset times or features."
        ),
        "labeled_positive": len(pos),
        "lead_time_governed": {
            "detected": len(leads),
            "quantiles_hours": _quantiles(leads),
            "first_alert_after_onset": sum(1 for x in leads if x < 0),
            "lead_ge_2h": sum(1 for x in leads if x >= 2),
            "lead_ge_4h": sum(1 for x in leads if x >= 4),
            "lead_ge_6h": sum(1 for x in leads if x >= 6),
            "histogram_hours": hist,
        },
        "lead_gated_min_2h": {
            "rule": "alert in [onset-12h, onset-2h]",
            "governed_sensitivity": _ci(
                lambda us: _sens(us, key="lead_gov", min_lead=MIN_LEAD_HOURS), units
            ),
            "interruptive_sensitivity": _ci(
                lambda us: _sens(us, key="lead_page", min_lead=MIN_LEAD_HOURS), units
            ),
        },
        "icd_label_sensitivity": {
            "pin": {"path": "eval/mimic_study/labels/frozen/icd_sepsis_codes.v1.json",
                    "sha256": _sha256(ICD_PIN_PATH)},
            "icd_positive": len(icd),
            "icd_and_sepsis3": len(overlap),
            "icd_only": len(icd) - len(overlap),
            "sepsis3_only": len(pos) - len(overlap),
            "any_governed_alert_during_stay": _ci(
                lambda us: _icd_any(us, key="any_gov"), units
            ),
            "any_interruptive_alert_during_stay": _ci(
                lambda us: _icd_any(us, key="any_page"), units
            ),
            "overlap_primary_window_governed": _rate(
                sum(1 for u in overlap if u["lead_gov"] is not None), len(overlap)
            ),
            "overlap_lead_ge_2h_governed": _rate(
                sum(1 for u in overlap if (u["lead_gov"] or -99) >= MIN_LEAD_HOURS),
                len(overlap),
            ),
        },
        "label_negative_alert_rates": _negative_rates(units),
    }


def _negative_rates(units: list[dict]) -> dict[str, Any]:
    """Share of label-negative stays with any alert: the specificity-side context."""
    out: dict[str, Any] = {}
    for label, key in (("icd_negative", "icd"), ("sepsis3_negative", "s3")):
        neg = [u for u in units if not u[key]]
        out[label] = {
            "stays": len(neg),
            "any_governed_alert": _rate(sum(1 for u in neg if u["any_gov"]), len(neg)),
            "any_interruptive_alert": _rate(sum(1 for u in neg if u["any_page"]), len(neg)),
        }
    return out


def build_subgroups(units: list[dict]) -> dict[str, Any]:
    def summarize(group: list[dict]) -> dict[str, Any]:
        pos = [u for u in group if u["s3"]]
        days = sum(u["days"] for u in group)
        pages = sum(u["pages"] for u in group)
        return {
            "stays": len(group) if len(group) >= MIN_CELL else None,
            "sepsis3_positive": len(pos) if len(pos) >= MIN_CELL else None,
            "governed_sensitivity": _rate(
                sum(1 for u in pos if u["lead_gov"] is not None), len(pos)
            ),
            "lead_ge_2h_governed_sensitivity": _rate(
                sum(1 for u in pos if (u["lead_gov"] or -99) >= MIN_LEAD_HOURS), len(pos)
            ),
            "interruptive_sensitivity": _rate(
                sum(1 for u in pos if u["lead_page"] is not None), len(pos)
            ),
            "interruptions_per_100_patient_days": (
                100.0 * pages / days if len(group) >= MIN_CELL and days > 0 else None
            ),
        }

    sexes = {"female": "F", "male": "M"}
    bands = [_age_band(lo) for lo, _ in AGE_BANDS]
    return {
        "role": "descriptive; not powered for between-group inference",
        "min_cell": MIN_CELL,
        "overall": summarize(units),
        "sex": {name: summarize([u for u in units if u["sex"] == code])
                for name, code in sexes.items()},
        "age_band": {band: summarize([u for u in units if u["age_band"] == band])
                     for band in bands},
    }


# --------------------------------------------------------------------------- audits


def build_completeness(mimic_audit: Path, eicu_check: Path) -> dict[str, Any]:
    mimic = json.loads(mimic_audit.read_text())
    eicu = json.loads(eicu_check.read_text())
    components = {
        name: {
            "stays_with_observation": comp["stays_with_observation"],
            "observation_rate": comp["observation_rate"],
            "first_day_rate": comp["first_day_rate"],
        }
        for name, comp in mimic["components"].items()
    }
    pressor = mimic["pressor_dose"]["classification"]
    return {
        "mimic_cohort_wide": {
            "source": {"path": "data/audit/mimic_completeness_audit.v1.json",
                       "sha256": _sha256(mimic_audit)},
            "cohort": "v1 audit selection",
            "stays": mimic["stays_in_audit"],
            "input_observation": components,
            "pressor_rows_known": pressor["known"],
            "pressor_rows_unknown": pressor["unknown"],
            "pressor_rows_unknown_units_per_hour": pressor["reason:unsupported_unit:units/hour"],
            "reconciliation_sample_stays": mimic["reconciliation"]["sample_stays"],
            "reconciliation_all_match": all(
                t["match"] for t in mimic["reconciliation"]["tables"].values()
            ),
        },
        "scored_samples": {
            "sample": {"limit": 8000, "seed": 42},
            "mimic": {
                "source": {"path": "data/audit/mimic_completeness_audit.v1.json",
                           "sha256": _sha256(mimic_audit)},
                "completeness": mimic["sample_replay"]["completeness"],
                "component_missing_rate": {
                    k: v["missing_rate"]
                    for k, v in mimic["sample_replay"]["components"].items()
                },
            },
            "eicu": {
                "source": {"path": "data/audit/eicu_completeness_check.v1.json",
                           "sha256": _sha256(eicu_check)},
                "dataset": "eICU-CRD 2.0",
                "completeness": eicu["missingness"]["completeness"],
                "component_missing_rate": {
                    k: v["missing_rate"] for k, v in eicu["missingness"]["components"].items()
                },
            },
        },
    }


# --------------------------------------------------------------------------- assemble


def build_publication_aggregates(
    *,
    index_dir: Path,
    labels_path: Path,
    test_rows_path: Path,
    mimic_audit: Path,
    eicu_check: Path,
) -> dict[str, Any]:
    import pyarrow.parquet as pq

    protocol = load_protocol(version="v2")
    stays = pq.read_table(index_dir / "stays.parquet").to_pylist()
    patients: dict[str, dict[str, Any]] = {}
    for row in pq.read_table(index_dir / "patients.parquet").to_pylist():
        extra = _extra(row)
        patients[str(row["subject_id"])] = {
            "anchor_age": row.get("anchor_age"),
            "anchor_year_group": row.get("anchor_year_group"),
            "gender": extra.get("gender"),
        }
    label_artifact = json.loads(labels_path.read_text())
    labels = {str(r["stay_id"]): r for r in label_artifact["stays"]}

    flow = build_cohort_flow(stays, patients, protocol=protocol)

    from eval.mimic_study.stage_b_run import split_stay_ids

    split_ids = split_stay_ids(index_dir, protocol=protocol, labels_path=labels_path)
    for split, ids in split_ids.items():
        if len(ids) != flow["split_counts"][split]:
            raise AssertionError(f"cohort flow disagrees with runner split for {split}")

    test_rows = json.loads(test_rows_path.read_text())["stays"]
    if len(test_rows) != len(split_ids["test"]):
        raise AssertionError("test replay rows do not cover the locked test split")
    units = stay_units(test_rows, patients)

    manifest = json.loads(MANIFEST_PATH.read_text())
    primary = manifest["test_primary"]
    check = _sens(units, key="lead_gov", min_lead=None)
    if abs(check - primary["governed_sensitivity"]) > 1e-12:
        raise AssertionError("replay rows do not reproduce the frozen governed sensitivity")

    meta = json.loads((index_dir / "meta.json").read_text())
    body = {
        "schema_version": "1.0.0",
        "artifact_id": "mimic_publication_aggregates.v1",
        "protocol_id": protocol["protocol_id"],
        "disclosure": f"aggregates only; cells < {MIN_CELL} stays suppressed (null)",
        "provenance": {
            "index_hash": meta.get("index_hash"),
            "labels_content_hash": label_artifact.get("content_hash"),
            "study_manifest": {"path": "eval/mimic_study/frozen/study_manifest.v3.json",
                               "content_hash": manifest["content_hash"]},
            "operating_point": {"path": "eval/mimic_study/frozen/operating_point.v2.json",
                                "sha256": _sha256(OPERATING_POINT_PATH)},
            "test_replay_rows_sha256": _sha256(test_rows_path),
            "regenerate_command": "make mimic-publication-aggregates",
        },
        "cohort_flow": flow,
        "characteristics": build_characteristics(stays, patients, labels, split_ids),
        "completeness": build_completeness(mimic_audit, eicu_check),
        "test_timing_and_labels": build_timing_and_labels(units),
        "test_subgroups": build_subgroups(units),
        "test_ablations": manifest["test_ablations"],
    }
    body["content_hash"] = stable_report_hash(body)
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, default=Path("data/index/mimic-iv"))
    parser.add_argument("--labels", type=Path, default=Path("data/stage_b/mimic_labels.v2.json"))
    parser.add_argument(
        "--test-rows", type=Path, default=Path("data/stage_b/fairness_rows.test.json")
    )
    parser.add_argument(
        "--mimic-audit", type=Path, default=Path("data/audit/mimic_completeness_audit.v1.json")
    )
    parser.add_argument(
        "--eicu-check", type=Path, default=Path("data/audit/eicu_completeness_check.v1.json")
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite frozen artifact {args.output}; bump the version")
    body = build_publication_aggregates(
        index_dir=args.index_dir,
        labels_path=args.labels,
        test_rows_path=args.test_rows,
        mimic_audit=args.mimic_audit,
        eicu_check=args.eicu_check,
    )
    args.output.write_text(json.dumps(body, indent=2) + "\n")
    print(json.dumps({"path": str(args.output), "content_hash": body["content_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
