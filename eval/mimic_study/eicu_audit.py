"""eICU portability/completeness audit (Phase A, eICU arm).

eICU is treated as an external completeness/portability analysis ONLY — not
clinical validation. Full-cohort eICU runs require credentialed eICU-CRD data
(``CURIE_EICU_DIR``); without it this module degrades to a demo smoke and records
the full-cohort run as blocked. Legacy "n=8000" eICU completeness numbers are NOT
reused unless a matching credentialed manifest exists; they are re-run here only
when the data is present.

AUDIT-ONLY output: written under ``data/audit/``; never frozen.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

N8000_LIMIT = 8000


def demo_portability_smoke(root: Path, *, limit_stays: int = 100) -> dict[str, Any]:
    """Convert + replay a bounded set of demo stays through the eICU adapter path."""
    from eval.mimic_harness.replay import replay_stay, result_to_public_dict
    from eval.sofa.scoring import SOFA_COMPONENTS
    from ingestion.adapters.eicu.convert import _iter_csv_gz, convert_eicu_rows

    patients: list[dict[str, str]] = []
    for row in _iter_csv_gz(root / "patient.csv.gz"):
        patients.append(row)
        if len(patients) >= limit_stays:
            break
    stay_ids = {p.get("patientunitstayid") or "" for p in patients}

    def _rows(table: str):
        src = root / table
        if not src.is_file():
            return iter(())
        return _iter_csv_gz(src)

    def _filtered(rows, key: str = "patientunitstayid"):
        for r in rows:
            if r.get(key) in stay_ids:
                yield r

    converted = convert_eicu_rows(
        patients=patients,
        labs=_filtered(_rows("lab.csv.gz")),
        vital_periodic=_filtered(_rows("vitalPeriodic.csv.gz")),
        vital_aperiodic=_filtered(_rows("vitalAperiodic.csv.gz")),
        nurse_charting=_filtered(_rows("nurseCharting.csv.gz")),
        respiratory_charting=_filtered(_rows("respiratoryCharting.csv.gz")),
        intake_output=_filtered(_rows("intakeOutput.csv.gz")),
        infusion_drug=_filtered(_rows("infusionDrug.csv.gz")),
        physical_exam=_filtered(_rows("physicalExam.csv.gz")),
        limit=None,
    )
    missing: Counter[str] = Counter()
    completeness: Counter[str] = Counter()
    n_scored = 0
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
        "dataset": "eicu-crd-demo",
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "role": "portability/completeness smoke only — not clinical validation",
        "stays_scored": n_scored,
        "completeness": dict(completeness),
        "components": rates,
    }


def full_eicu_status() -> dict[str, Any]:
    """Report whether credentialed eICU is available; record the n=8000 re-run status."""
    from ingestion.adapters.eicu.paths import eicu_dir, require_eicu_dir

    status: dict[str, Any] = {
        "dataset": "eicu-crd-full",
        "available": False,
        "n8000_claims_rerun": "blocked",
        "n8000_claims_verdict": (
            "Legacy n=8000 eICU completeness numbers (implementation-backlog.md "
            "Milestone 11) CANNOT be re-run: credentialed eICU-CRD data is not "
            "present (CURIE_EICU_DIR unset). The old numbers are marked unverified "
            "until a credentialed manifest-backed rerun exists."
        ),
    }
    try:
        root = eicu_dir()
    except FileNotFoundError as exc:
        status["block_reason"] = str(exc)
        return status
    try:
        root = require_eicu_dir()
    except FileNotFoundError as exc:
        status["block_reason"] = str(exc)
        return status
    status["available"] = True
    status["root"] = str(root)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="eICU portability/completeness audit")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--limit-stays", type=int, default=100)
    args = parser.parse_args(argv)

    from ingestion.adapters.eicu.paths import require_eicu_demo_dir

    out: dict[str, Any] = {
        "status": "AUDIT_ONLY_NOT_FROZEN",
        "full_cohort": full_eicu_status(),
    }
    try:
        demo_root = require_eicu_demo_dir()
        out["demo_smoke"] = demo_portability_smoke(demo_root, limit_stays=args.limit_stays)
    except FileNotFoundError as exc:
        out["demo_smoke"] = {"error": str(exc)}

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
