"""Score SOFA + AKI on MIMIC-IV demo ICU stays (local PhysioNet open demo)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from eval.aki.scoring import compute_aki_score, tier_for_aki_score
from eval.indicators.registry import load_rule_bundle
from eval.sofa.scoring import compute_sofa_score, tier_for_score
from ingestion.adapters.mimic import item_map as im
from ingestion.adapters.mimic.extract import build_aki_input, build_sofa_inputs
from ingestion.adapters.mimic.loader import (
    index_chartevents,
    index_inputevents_pressors,
    index_labevents,
    index_outputevents_urine,
    load_icustays,
)
from ingestion.adapters.mimic.paths import require_mimic_demo_dir


def _as_of_for_stay(stay: dict[str, str]) -> datetime:
    """Score near end of ICU stay (or intime+24h if short)."""
    intime = datetime.strptime(stay["intime"], "%Y-%m-%d %H:%M:%S")
    outtime = datetime.strptime(stay["outtime"], "%Y-%m-%d %H:%M:%S")
    # Prefer 24h after admit if stay long enough; else midpoint/outtime
    candidate = datetime.fromtimestamp(intime.timestamp() + 24 * 3600)
    if candidate <= outtime:
        return candidate
    return outtime


def run_mimic_demo(*, limit: int | None = None) -> dict:
    root = require_mimic_demo_dir()
    sofa_bundle = load_rule_bundle("sepsis-sofa")
    aki_bundle = load_rule_bundle("aki-kdigo")

    stays = load_icustays(root, limit=limit)
    subject_ids = {s["subject_id"] for s in stays}
    stay_ids = {s["stay_id"] for s in stays}

    lab_itemids = im.LAB_CREATININE | im.LAB_PLATELETS | im.LAB_BILIRUBIN_TOTAL
    chart_itemids = (
        im.CHART_MAP
        | im.CHART_SPO2
        | im.CHART_FIO2
        | im.CHART_GCS_EYE
        | im.CHART_GCS_VERBAL
        | im.CHART_GCS_MOTOR
        | im.CHART_CREATININE
        | im.CHART_BILIRUBIN
        | im.CHART_PLATELETS
    )

    labs_by_subject = index_labevents(root, subject_ids=subject_ids, itemids=lab_itemids)
    charts_by_stay = index_chartevents(root, stay_ids=stay_ids, itemids=chart_itemids)
    inputs_by_stay = index_inputevents_pressors(
        root, stay_ids=stay_ids, itemids=set(im.INPUT_VASOPRESSORS)
    )
    outputs_by_stay = index_outputevents_urine(
        root, stay_ids=stay_ids, itemids=im.OUTPUT_URINE
    )

    rows: list[dict] = []
    sofa_alertable = 0
    aki_alertable = 0
    sofa_partial = 0
    aki_partial = 0

    for stay in stays:
        as_of = _as_of_for_stay(stay)
        sid = stay["subject_id"]
        stay_id = stay["stay_id"]
        # Labs for this admission when hadm present; else all subject labs
        hadm = stay.get("hadm_id") or ""
        lab_rows = [
            r
            for r in labs_by_subject.get(sid, [])
            if not hadm or r.get("hadm_id") in {"", hadm}
        ]
        sofa_inputs = build_sofa_inputs(
            as_of=as_of,
            lab_rows=lab_rows,
            chart_rows=charts_by_stay.get(stay_id, []),
            input_rows=inputs_by_stay.get(stay_id, []),
            output_rows=outputs_by_stay.get(stay_id, []),
        )
        sofa = compute_sofa_score(
            patient_id=f"Patient/{sid}",
            encounter_id=f"Encounter/{hadm}" if hadm else f"ICUStay/{stay_id}",
            event_time=as_of,
            inputs=sofa_inputs,
            rule_bundle_id=sofa_bundle["bundle_id"],
            rule_version=sofa_bundle["version"],
        )
        aki_in = build_aki_input(
            as_of=as_of,
            lab_rows=lab_rows,
            chart_rows=charts_by_stay.get(stay_id, []),
        )
        aki = compute_aki_score(
            patient_id=f"Patient/{sid}",
            encounter_id=f"Encounter/{hadm}" if hadm else f"ICUStay/{stay_id}",
            event_time=as_of,
            inputs=aki_in,
            rule_bundle_id=aki_bundle["bundle_id"],
            rule_version=aki_bundle["version"],
        )
        sofa_tier = tier_for_score(sofa.total_score)
        aki_tier = tier_for_aki_score(aki.total_score)
        if sofa.completeness.value == "partial":
            sofa_partial += 1
        if aki.completeness.value == "partial":
            aki_partial += 1
        if sofa_tier.value != "none":
            sofa_alertable += 1
        if aki_tier.value != "none":
            aki_alertable += 1
        rows.append(
            {
                "subject_id": sid,
                "stay_id": stay_id,
                "hadm_id": hadm,
                "as_of": as_of.isoformat(sep=" "),
                "sofa_score": sofa.total_score,
                "sofa_completeness": sofa.completeness.value,
                "sofa_missing": [c.value for c in sofa.missing_components],
                "sofa_tier": sofa_tier.value,
                "aki_stage": aki.stage,
                "aki_score": aki.total_score,
                "aki_completeness": aki.completeness.value,
                "aki_missing": aki.missing_components,
                "aki_tier": aki_tier.value,
            }
        )

    return {
        "source": str(root),
        "dataset": "mimic-iv-clinical-database-demo",
        "stays_scored": len(rows),
        "totals": {
            "sofa_alertable": sofa_alertable,
            "aki_alertable": aki_alertable,
            "sofa_partial": sofa_partial,
            "aki_partial": aki_partial,
        },
        "rule_bundles": {
            "sepsis-sofa": sofa_bundle["version"],
            "aki-kdigo": aki_bundle["version"],
        },
        "stays": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score MIMIC-IV demo with Curie rules")
    parser.add_argument("--limit", type=int, default=None, help="Max ICU stays")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)
    report = run_mimic_demo(limit=args.limit)
    print(
        json.dumps(
            {
                "source": report["source"],
                "stays_scored": report["stays_scored"],
                "totals": report["totals"],
                "rule_bundles": report["rule_bundles"],
            },
            indent=2,
        )
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
