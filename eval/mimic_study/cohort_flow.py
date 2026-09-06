"""Cohort-flow audit for the frozen MIMIC-IV protocol (Phase A item 1/2).

Applies the frozen ``eval/mimic_study/frozen/protocol.v1.json`` cohort rules to the
credentialed MIMIC-IV 3.1 source files and reports a denominator at every exclusion
step, split assignment by ICU intime, and the declared ESRD / comfort-care /
OR-transfer handling.

AUDIT-ONLY OUTPUT: results are written under ``data/audit/`` and are NOT frozen
study numbers. Freezing requires the Phase B/C integration gate (see plan
``docs/superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md``).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.mimic_study.protocol import load_protocol, split_for_anchor_year_group
from ingestion.adapters.mimic.loader import iter_csv_gz
from ingestion.adapters.mimic.paths import require_mimic_dir

MIN_AGE_YEARS = 18
MIN_LOS_HOURS = 4.0

# Declared ESRD-on-dialysis ICD codes (pinned policy for this audit; ICD-9/10 pairs).
ESRD_ICD_CODES = {
    "5856",  # Chronic kidney disease, stage V (ICD-9)
    "585.6",
    "Z992",  # Dependence on renal dialysis (ICD-10)
    "Z49",
    "Z4931",
    "Z4901",
    "Z4902",
}
COMFORT_CARE_ICD_CODES = {
    "V667",  # Encounter for palliative care (ICD-9)
    "Z515",  # Encounter for palliative care (ICD-10)
}
OR_CAREUNITS = {"OR", "PACU", "Operating Room", "Post Anesthesia Care Unit"}

SPLIT_RANGES = {
    "development": ("2008-01-01", "2016-12-31"),
    "calibration": ("2017-01-01", "2018-12-31"),
    "test": ("2019-01-01", "2019-12-31"),
}
# Exclusive upper bound = first day of the next split.
_SPLIT_BOUNDS = {
    "development": ("2008-01-01", "2017-01-01"),
    "calibration": ("2017-01-01", "2019-01-01"),
    "test": ("2019-01-01", "2020-01-01"),
}

# MIMIC-IV 3.1 de-identifies dates with a per-subject random shift (2100-2200), so
# cross-patient calendar comparison is impossible. The frozen protocol's calendar
# split ranges cannot be applied; ``anchor_year_group`` is the only 3-year temporal
# alignment the release provides. Split-dependent analyses are SUSPENDED until a
# protocol amendment picks a legal split scheme (see cohort-flow audit output).
SPLIT_STATUS = "suspended_pending_protocol_amendment"
SPLIT_FINDING = (
    "MIMIC-IV v3.1 shifts all dates independently per subject (deidentified years "
    "2100-2200); distinct patients are not temporally comparable. Frozen protocol v1 "
    "calendar split ranges (2008-2019 by ICU intime) are inapplicable. Only "
    "anchor_year_group (3-year buckets) preserves approximate temporal order. Split "
    "assignment requires a protocol amendment before any split-dependent metric can "
    "be generated or frozen."
)


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _split_for_intime(intime: datetime) -> str:
    for split_id, (lo, hi) in _SPLIT_BOUNDS.items():
        if _parse_ts(lo) <= intime < _parse_ts(hi):
            return split_id
    return "outside_split_ranges"


def load_esrd_and_comfort_flags(root: Path) -> tuple[set[str], set[str]]:
    """subject_id sets flagged by any pinned ICD code in diagnoses_icd."""
    esrd: set[str] = set()
    comfort: set[str] = set()
    esrd_norm = {c.replace(".", "").upper() for c in ESRD_ICD_CODES}
    comfort_norm = {c.replace(".", "").upper() for c in COMFORT_CARE_ICD_CODES}
    path = root / "hosp" / "diagnoses_icd.csv.gz"
    if not path.is_file():
        return esrd, comfort
    for row in iter_csv_gz(path):
        code = (row.get("icd_code") or "").strip().replace(".", "").upper()
        sid = row.get("subject_id") or ""
        if not sid or not code:
            continue
        if code in esrd_norm:
            esrd.add(sid)
        if code in comfort_norm:
            comfort.add(sid)
    return esrd, comfort


def apply_cohort(
    root: Path,
    *,
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return cohort flow counts plus the surviving stay rows (dicts)."""
    proto = protocol or load_protocol()
    patients = list(iter_csv_gz(root / "hosp" / "patients.csv.gz"))
    admissions = list(iter_csv_gz(root / "hosp" / "admissions.csv.gz"))
    icustays = list(iter_csv_gz(root / "icu" / "icustays.csv.gz"))

    n_patients = len(patients)
    n_admissions = len(admissions)
    n_icustays = len(icustays)

    esrd_sids, comfort_sids = load_esrd_and_comfort_flags(root)

    anchor_age = {
        (r.get("subject_id") or ""): _to_int(r.get("anchor_age"))
        for r in patients
    }
    anchor_group = {
        (r.get("subject_id") or ""): (r.get("anchor_year_group") or "").strip()
        for r in patients
    }

    # icustays joined with admission + age
    hadm_keep: dict[str, list[dict[str, Any]]] = {}
    n_missing_admission_link = 0
    n_pediatric_excluded = 0
    for r in icustays:
        sid = r.get("subject_id") or ""
        age = anchor_age.get(sid)
        hadm = r.get("hadm_id") or ""
        if not hadm:
            n_missing_admission_link += 1
            continue
        if age is None or age < MIN_AGE_YEARS:
            n_pediatric_excluded += 1
            continue
        hadm_keep.setdefault(hadm, []).append((sid, r))

    n_first_stay_kept = 0
    n_later_stay_excluded = 0
    first_by_hadm: dict[str, tuple[str, dict[str, Any]]] = {}
    for hadm, entries in hadm_keep.items():
        entries.sort(key=lambda e: (_parse_ts(e[1].get("intime")) or datetime.max))
        first_by_hadm[hadm] = entries[0]
        n_first_stay_kept += 1
        n_later_stay_excluded += max(0, len(entries) - 1)

    n_invalid_times = 0
    n_short_los = 0
    kept: list[dict[str, Any]] = []
    for hadm, (sid, r) in first_by_hadm.items():
        intime = _parse_ts(r.get("intime"))
        outtime = _parse_ts(r.get("outtime"))
        if intime is None or outtime is None or outtime < intime:
            n_invalid_times += 1
            continue
        if (outtime - intime).total_seconds() < MIN_LOS_HOURS * 3600:
            n_short_los += 1
            continue
        kept.append(
            {
                "stay_id": r.get("stay_id") or "",
                "subject_id": sid,
                "hadm_id": hadm,
                "intime": r.get("intime") or "",
                "outtime": r.get("outtime") or "",
                "anchor_year_group": anchor_group.get(sid, ""),
                "split_id": "",
                "first_careunit": r.get("first_careunit") or "",
                "last_careunit": r.get("last_careunit") or "",
                "esrd_on_dialysis": sid in esrd_sids,
                "comfort_care": sid in comfort_sids,
                "or_transfer_gap_flagged": (r.get("first_careunit") or "").strip()
                in OR_CAREUNITS,
            }
        )

    use_anchor_groups = (proto.get("splits") or {}).get("scheme") == "anchor_year_group"
    split_counts: Counter[str] = Counter(
        {k: 0 for k in ("development", "calibration", "test")}
    )
    for r in kept:
        split_id = (
            split_for_anchor_year_group(r["anchor_year_group"], proto)
            if use_anchor_groups
            else _split_for_intime(_parse_ts(r["intime"]))
        )
        r["split_id"] = split_id
        split_counts[split_id] += 1

    group_counts: Counter[str] = Counter(r["anchor_year_group"] for r in kept)

    return {
        "protocol_id": proto["protocol_id"],
        "dataset": "mimic-iv-3.1",
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "cohort_flow": {
            "patients_source": n_patients,
            "admissions_source": n_admissions,
            "icustays_source": n_icustays,
            "excluded_missing_hadm_id": n_missing_admission_link,
            "excluded_pediatric_or_unknown_age": n_pediatric_excluded,
            "adult_icustays_with_admission": n_first_stay_kept + n_later_stay_excluded,
            "excluded_later_icu_stays_same_admission": n_later_stay_excluded,
            "first_icu_stay_per_admission": n_first_stay_kept,
            "excluded_invalid_intime_outtime": n_invalid_times,
            "excluded_los_under_4h": n_short_los,
            "final_cohort_stays": len(kept),
        },
        "declared_handling": {
            "esrd_on_dialysis": {
                "policy": "exclude from AKI denominator; report as subgroup",
                "icd_codes_pinned": sorted(ESRD_ICD_CODES),
                "flagged_stays": sum(1 for r in kept if r["esrd_on_dialysis"]),
            },
            "comfort_care": {
                "policy": "subgroup + suppression analysis; not hard-excluded",
                "icd_codes_pinned": sorted(COMFORT_CARE_ICD_CODES),
                "flagged_stays": sum(1 for r in kept if r["comfort_care"]),
            },
            "or_transfer_gaps": {
                "policy": "report missingness; do not impute",
                "first_careunit_flagged_stays": sum(
                    1 for r in kept if r["or_transfer_gap_flagged"]
                ),
                "careunits_pinned": sorted(OR_CAREUNITS),
            },
        },
        "splits": {
            "status": "frozen" if use_anchor_groups else SPLIT_STATUS,
            "finding": None if use_anchor_groups else SPLIT_FINDING,
            "split_counts": dict(sorted(split_counts.items())),
            "frozen_ranges_inapplicable": (
                {} if use_anchor_groups else dict(sorted(split_counts.items()))
            ),
            "anchor_year_group_counts": dict(sorted(group_counts.items())),
        },
        "split_ranges_frozen": {} if use_anchor_groups else SPLIT_RANGES,
        "stays": kept,
    }


def _to_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIMIC cohort-flow audit (not frozen)")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--no-stays", action="store_true", help="omit the per-stay list")
    args = parser.parse_args(argv)

    root = require_mimic_dir()
    print(f"applying cohort on {root}", flush=True)
    out = apply_cohort(root)
    if args.no_stays:
        out.pop("stays", None)
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
