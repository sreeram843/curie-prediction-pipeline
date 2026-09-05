"""Matched MIMIC / eICU cohort filters for completeness comparisons (CURIE-049).

Protocol (MIMIC-IV study): adult (age >= 18), first ICU stay per hospital admission,
LOS >= 4 hours. Completeness samples must use this filter and a seeded random draw —
never first-N file order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ingestion.completeness import (
    DEFAULT_SAMPLE_SEED,
    eicu_protocol_eligible,
    filter_eicu_protocol_cohort,
    filter_mimic_protocol_cohort,
    load_csv_gz,
    parse_eicu_age_years,
    sample_eicu_protocol_patients,
    sample_mimic_protocol_stays,
    seeded_sample,
)

__all__ = [
    "DEFAULT_SAMPLE_SEED",
    "eicu_protocol_eligible",
    "filter_eicu_protocol_cohort",
    "filter_mimic_protocol_cohort",
    "load_csv_gz",
    "parse_eicu_age_years",
    "sample_eicu_protocol_patients",
    "sample_mimic_protocol_stays",
    "seeded_sample",
    "sofa_component_missing_rates",
]


def _adult_first_stay_cohort(
    *,
    icustays: list[dict[str, str]],
    patients: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Compatibility alias used by Milestone 11 completeness comparisons."""
    return filter_mimic_protocol_cohort(icustays=icustays, patients=patients)


def sofa_component_missing_rates(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Stay-level SOFA component missingness from harness public result dicts.

    A stay counts as missing a component when the final snapshot lists it in
    ``missing_components`` (same denominator as Milestone 11 n=8000 cards).
    """
    from collections import Counter

    from eval.sofa.scoring import SOFA_COMPONENTS

    n = len(results)
    missing = Counter()
    completeness: Counter[str] = Counter()
    for row in results:
        snap = row.get("final_snapshot") or {}
        if not snap and row.get("snapshots"):
            snap = row["snapshots"][-1] or {}
        completeness[str(snap.get("completeness") or "unknown")] += 1
        for component in snap.get("missing_components") or []:
            missing[str(component)] += 1

    rates = {
        name.value: {
            "missing_stays": int(missing.get(name.value, 0)),
            "missing_rate": (missing.get(name.value, 0) / n) if n else 0.0,
        }
        for name in SOFA_COMPONENTS
    }
    return {
        "stays_scored": n,
        "completeness": dict(completeness),
        "components": rates,
    }



def measure_eicu_sofa_missingness(
    root: Path,
    *,
    limit: int = 8000,
    seed: int = DEFAULT_SAMPLE_SEED,
    batch_size: int = 200,
) -> dict[str, Any]:
    """Protocol-seeded eICU SOFA missingness.

    One pass over each source CSV shards rows into batch files, then converts
    each batch from those shards (avoids OOM and 40× full-file rescans).
    """
    import csv
    import gzip
    import shutil
    import tempfile
    from collections import Counter

    from eval.mimic_harness.replay import replay_stay, result_to_public_dict
    from eval.sofa.scoring import SOFA_COMPONENTS
    from ingestion.adapters.eicu.convert import _iter_csv_gz, convert_eicu_rows

    patients = sample_eicu_protocol_patients(root, limit=limit, seed=seed)
    stay_to_batch: dict[str, int] = {}
    batches: list[list[dict[str, str]]] = []
    for i in range(0, len(patients), batch_size):
        batch = patients[i : i + batch_size]
        batches.append(batch)
        bi = len(batches) - 1
        for p_row in batch:
            sid = (p_row.get("patientunitstayid") or "").strip()
            if sid:
                stay_to_batch[sid] = bi

    tables = (
        "lab.csv.gz",
        "vitalPeriodic.csv.gz",
        "vitalAperiodic.csv.gz",
        "nurseCharting.csv.gz",
        "respiratoryCharting.csv.gz",
        "intakeOutput.csv.gz",
        "infusionDrug.csv.gz",
        "physicalExam.csv.gz",
    )
    tmp = Path(tempfile.mkdtemp(prefix="curie-eicu-shards-"))
    try:
        for table in tables:
            src = root / table
            if not src.is_file():
                print(f"skip missing {table}", flush=True)
                continue
            print(f"sharding {table} ...", flush=True)
            n_kept = 0
            n_seen = 0
            table_writers: dict[int, Any] = {}
            # Hourly downsample for high-frequency vitals (SOFA uses latest-before).
            hourly_seen: set[tuple[str, int]] = set()
            downsample = table in {
                "vitalPeriodic.csv.gz",
                "vitalAperiodic.csv.gz",
            }
            try:
                for row in _iter_csv_gz(src):
                    sid = (row.get("patientunitstayid") or "").strip()
                    bi = stay_to_batch.get(sid)
                    if bi is None:
                        continue
                    # Keep only SOFA-relevant rows (cuts nurseCharting ~10×).
                    if table == "nurseCharting.csv.gz":
                        lab = (row.get("nursingchartcelltypevallabel") or "").lower()
                        nam = (row.get("nursingchartcelltypevalname") or "").lower()
                        blob = f"{lab} {nam}"
                        if not (
                            "gcs" in blob
                            or "glasgow" in blob
                            or lab == "o2 saturation"
                            or "map (mmhg)" in blob
                        ):
                            continue
                    elif table == "respiratoryCharting.csv.gz":
                        lab = (row.get("respchartvaluelabel") or "").strip().lower()
                        if lab not in {
                            "fio2",
                            "fio2 (%)",
                            "fio2(%)",
                            "o2 percentage",
                            "o2 %",
                        }:
                            continue
                    elif table == "intakeOutput.csv.gz":
                        if (row.get("celllabel") or "").strip().lower() != "urine":
                            continue
                    elif table == "lab.csv.gz":
                        name = (row.get("labname") or "").strip().lower()
                        if name not in {
                            "creatinine",
                            "platelets x 1000",
                            "total bilirubin",
                            "fio2",
                            "pao2",
                        }:
                            continue
                    elif table == "physicalExam.csv.gz":
                        path_l = (row.get("physicalexampath") or "").lower()
                        if "/gcs/" not in path_l and "glasgow" not in path_l:
                            continue
                    elif table == "infusionDrug.csv.gz":
                        drug = (row.get("drugname") or "").lower()
                        if not any(
                            a in drug
                            for a in (
                                "norepinephrine",
                                "epinephrine",
                                "dopamine",
                                "dobutamine",
                                "phenylephrine",
                                "vasopressin",
                            )
                        ):
                            continue
                    n_seen += 1
                    if downsample:
                        raw_off = (row.get("observationoffset") or "").strip()
                        try:
                            hour = int(float(raw_off)) // 60
                        except ValueError:
                            hour = 0
                        key = (sid, hour)
                        if key in hourly_seen:
                            continue
                        hourly_seen.add(key)
                    handle = table_writers.get(bi)
                    if handle is None:
                        path = tmp / f"b{bi}_{table}"
                        fh = gzip.open(path, "wt", newline="")
                        dw = csv.DictWriter(fh, fieldnames=list(row.keys()))
                        dw.writeheader()
                        table_writers[bi] = (fh, dw)
                    else:
                        fh, dw = handle
                    dw.writerow(row)
                    n_kept += 1
            finally:
                for fh, _dw in table_writers.values():
                    fh.close()
            if downsample:
                print(f"  kept {n_kept:,} rows (hourly from {n_seen:,})", flush=True)
            else:
                print(f"  kept {n_kept:,} rows", flush=True)

        missing: Counter[str] = Counter()
        completeness: Counter[str] = Counter()
        concept_counts: Counter[str] = Counter()
        n_scored = 0
        for bi, batch in enumerate(batches):
            print(f"eICU convert+replay batch {bi + 1}/{len(batches)}", flush=True)

            def _rows(table: str):
                path = tmp / f"b{bi}_{table}"
                if not path.is_file():
                    return iter(())
                return _iter_csv_gz(path)

            converted = convert_eicu_rows(
                patients=batch,
                labs=_rows("lab.csv.gz"),
                vital_periodic=_rows("vitalPeriodic.csv.gz"),
                vital_aperiodic=_rows("vitalAperiodic.csv.gz"),
                nurse_charting=_rows("nurseCharting.csv.gz"),
                respiratory_charting=_rows("respiratoryCharting.csv.gz"),
                intake_output=_rows("intakeOutput.csv.gz"),
                infusion_drug=_rows("infusionDrug.csv.gz"),
                physical_exam=_rows("physicalExam.csv.gz"),
                limit=None,
            )
            for concept, count in (converted.get("coverage") or {}).get("concepts", {}).items():
                concept_counts[str(concept)] += int(count)
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
        "dataset": "eicu-crd",
        "cohort": "protocol_seeded",
        "limit": limit,
        "seed": seed,
        "batch_size": batch_size,
        "coverage": {"concepts": dict(concept_counts), "stays": n_scored},
        "missingness": {
            "stays_scored": n_scored,
            "completeness": dict(completeness),
            "components": rates,
        },
    }


def measure_mimic_sofa_missingness(
    root: Path,
    *,
    limit: int = 8000,
    seed: int = DEFAULT_SAMPLE_SEED,
    batch_size: int = 200,
) -> dict[str, Any]:
    """Protocol-seeded MIMIC SOFA missingness (batched to bound memory)."""
    from collections import Counter

    from eval.mimic_harness.replay import replay_stay, result_to_public_dict
    from eval.sofa.scoring import SOFA_COMPONENTS
    from ingestion.adapters.mimic.to_demo_schema import convert_mimic_demo

    stays = sample_mimic_protocol_stays(root, limit=limit, seed=seed)
    missing = Counter()
    completeness: Counter[str] = Counter()
    concept_counts: Counter[str] = Counter()
    n_scored = 0
    n_batches = (len(stays) + batch_size - 1) // batch_size
    for bi in range(n_batches):
        batch = stays[bi * batch_size : (bi + 1) * batch_size]
        print(f"MIMIC batch {bi + 1}/{n_batches} stays={len(batch)}", flush=True)
        converted = convert_mimic_demo(root, stays=batch)
        for concept, count in (converted.get("coverage") or {}).get("concepts", {}).items():
            concept_counts[str(concept)] += int(count)
        for stay in converted["stays"]:
            row = result_to_public_dict(replay_stay(stay, score_every_event=False))
            snap = row.get("final_snapshot") or {}
            completeness[str(snap.get("completeness") or "unknown")] += 1
            for component in snap.get("missing_components") or []:
                missing[str(component)] += 1
            n_scored += 1

    rates = {
        name.value: {
            "missing_stays": int(missing.get(name.value, 0)),
            "missing_rate": (missing.get(name.value, 0) / n_scored) if n_scored else 0.0,
        }
        for name in SOFA_COMPONENTS
    }
    return {
        "dataset": "mimic-iv",
        "cohort": "protocol_seeded",
        "limit": limit,
        "seed": seed,
        "batch_size": batch_size,
        "coverage": {"concepts": dict(concept_counts), "stays": n_scored},
        "missingness": {
            "stays_scored": n_scored,
            "completeness": dict(completeness),
            "components": rates,
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="SOFA component missingness (protocol cohort)")
    parser.add_argument("--dataset", choices=("eicu", "mimic", "both"), default="eicu")
    parser.add_argument("--limit", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SAMPLE_SEED)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args(argv)

    reports: list[dict[str, Any]] = []
    if args.dataset in {"eicu", "both"}:
        from ingestion.adapters.eicu.paths import require_eicu_dir

        eicu_root = require_eicu_dir()
        print(f"measuring eICU at {eicu_root} limit={args.limit}", flush=True)
        reports.append(
            measure_eicu_sofa_missingness(
                eicu_root, limit=args.limit, seed=args.seed, batch_size=args.batch_size
            )
        )
    if args.dataset in {"mimic", "both"}:
        from ingestion.adapters.mimic.paths import require_mimic_dir

        mimic_root = require_mimic_dir()
        print(f"measuring MIMIC at {mimic_root} limit={args.limit}", flush=True)
        reports.append(
            measure_mimic_sofa_missingness(
                mimic_root, limit=args.limit, seed=args.seed, batch_size=args.batch_size
            )
        )

    payload = reports[0] if len(reports) == 1 else {"reports": reports}
    text_out = json.dumps(payload, indent=2)
    print(text_out, flush=True)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text_out + chr(10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
