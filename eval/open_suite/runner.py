"""CLI: score every open dataset present under data/."""

from __future__ import annotations

import argparse
import json
import traceback
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import replay_stay, result_to_public_dict
from eval.open_suite.coverage import summarize_challenge_report, summarize_harness_results
from ingestion.adapters.challenge2019.loader import default_archive_dir
from ingestion.adapters.eicu.paths import eicu_demo_dir
from ingestion.adapters.mimic.paths import mimic_demo_dir
from ingestion.adapters.mimic_fhir.paths import mimic_fhir_demo_dir
from ingestion.adapters.syn_icu.paths import CORE_TABLES, syn_icu_dir
from ingestion.adapters.synthea.bundle_loader import load_envelopes_from_dir

REPO = Path(__file__).resolve().parents[2]
SYNTHEA_DIR = REPO / "data" / "synthea" / "fhir"


def _harness_card(
    *,
    dataset_id: str,
    title: str,
    converted: dict[str, Any],
) -> dict[str, Any]:
    results = [result_to_public_dict(replay_stay(stay)) for stay in converted["stays"]]
    return {
        "id": dataset_id,
        "title": title,
        "status": "ok",
        "metric_family": "plumbing",
        "dataset_pin": converted.get("dataset_pin"),
        "coverage": converted.get("coverage"),
        "warnings": converted.get("warnings") or [],
        "metrics": summarize_harness_results(results),
    }


def probe() -> list[dict[str, Any]]:
    syn_root = syn_icu_dir()
    syn_ok = syn_root.is_dir() and (syn_root / "syn_icustays.xlsx").is_file()
    challenge_root = default_archive_dir()
    challenge_ok = (challenge_root / "training_setA").is_dir() or (
        challenge_root / "training_setB"
    ).is_dir()
    return [
        {
            "id": "challenge-2019",
            "present": challenge_ok,
            "path": str(challenge_root),
            "metric_family": "detection",
        },
        {
            "id": "mimic-iv-demo",
            "present": (mimic_demo_dir() / "icu").is_dir(),
            "path": str(mimic_demo_dir()),
            "metric_family": "plumbing",
        },
        {
            "id": "mimic-iv-fhir-demo",
            "present": (mimic_fhir_demo_dir() / "fhir" / "MimicEncounterICU.ndjson.gz").is_file(),
            "path": str(mimic_fhir_demo_dir()),
            "metric_family": "plumbing",
        },
        {
            "id": "eicu-crd-demo",
            "present": (eicu_demo_dir() / "patient.csv.gz").is_file(),
            "path": str(eicu_demo_dir()),
            "metric_family": "plumbing",
        },
        {
            "id": "syn-icu",
            "present": syn_ok,
            "path": str(syn_root),
            "metric_family": "plumbing",
            "required_tables": list(CORE_TABLES),
        },
        {
            "id": "synthea",
            "present": SYNTHEA_DIR.is_dir() and any(SYNTHEA_DIR.glob("*.json")),
            "path": str(SYNTHEA_DIR),
            "metric_family": "envelope",
        },
    ]


def _run_challenge(*, limit: int | None) -> dict[str, Any]:
    from eval.challenge2019.runner import run_challenge2019_eval

    report = run_challenge2019_eval(
        limit=limit,
        gov_profile="accuracy",
        bootstrap_samples=0,
    )
    return {
        "id": "challenge-2019",
        "title": "PhysioNet Challenge 2019",
        "status": "ok",
        "metric_family": "detection",
        "metrics": summarize_challenge_report(report),
        "notes": report.get("notes") or [],
    }


def _run_mimic_demo(*, limit: int | None) -> dict[str, Any]:
    from ingestion.adapters.mimic.to_demo_schema import convert_mimic_demo

    return _harness_card(
        dataset_id="mimic-iv-demo",
        title="MIMIC-IV Clinical Database Demo (CSV)",
        converted=convert_mimic_demo(limit=limit),
    )


def _run_mimic_fhir(*, limit: int | None) -> dict[str, Any]:
    from ingestion.adapters.mimic_fhir.convert import convert_mimic_fhir

    return _harness_card(
        dataset_id="mimic-iv-fhir-demo",
        title="MIMIC-IV Clinical Database Demo on FHIR",
        converted=convert_mimic_fhir(limit=limit),
    )


def _run_eicu(*, limit: int | None) -> dict[str, Any]:
    from ingestion.adapters.eicu.convert import convert_eicu

    return _harness_card(
        dataset_id="eicu-crd-demo",
        title="eICU Collaborative Research Database Demo",
        converted=convert_eicu(limit=limit),
    )


def _run_syn_icu(*, limit: int | None) -> dict[str, Any]:
    from ingestion.adapters.syn_icu.convert import convert_syn_icu

    return _harness_card(
        dataset_id="syn-icu",
        title="SYN-ICU (synthetic K-MIMIC)",
        converted=convert_syn_icu(limit=limit),
    )


def _run_synthea(*, limit: int | None) -> dict[str, Any]:
    envelopes = load_envelopes_from_dir(SYNTHEA_DIR)
    if limit is not None:
        envelopes = envelopes[:limit]
    types = Counter(e.resource_type for e in envelopes)
    patients = {e.patient_id for e in envelopes}
    return {
        "id": "synthea",
        "title": "Synthea synthetic FHIR",
        "status": "ok",
        "metric_family": "envelope",
        "metrics": {
            "metric_family": "envelope",
            "bundle_files": len(list(SYNTHEA_DIR.glob("*.json"))),
            "envelopes": len(envelopes),
            "patients": len(patients),
            "resource_types": dict(types),
        },
        "notes": [
            "Synthea is FHIR envelope plumbing, not an ICU SOFA/AKI labeled eval."
        ],
    }


_RUNNERS: dict[str, Callable[..., dict[str, Any]]] = {
    "challenge-2019": _run_challenge,
    "mimic-iv-demo": _run_mimic_demo,
    "mimic-iv-fhir-demo": _run_mimic_fhir,
    "eicu-crd-demo": _run_eicu,
    "syn-icu": _run_syn_icu,
    "synthea": _run_synthea,
}


def run_open_suite(
    *,
    limit: int | None = 50,
    challenge_limit: int | None = 200,
    only: set[str] | None = None,
) -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    for spec in probe():
        dataset_id = spec["id"]
        if only is not None and dataset_id not in only:
            continue
        if not spec["present"]:
            datasets.append(
                {
                    "id": dataset_id,
                    "status": "skipped",
                    "reason": f"data not found at {spec['path']}",
                    "metric_family": spec["metric_family"],
                }
            )
            continue
        cap = challenge_limit if dataset_id == "challenge-2019" else limit
        try:
            datasets.append(_RUNNERS[dataset_id](limit=cap))
        except Exception as exc:  # noqa: BLE001 — suite continues on one dataset failure
            datasets.append(
                {
                    "id": dataset_id,
                    "status": "error",
                    "reason": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                    "metric_family": spec["metric_family"],
                }
            )

    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "disclaimer": (
            "Open / synthetic evals only. Challenge 2019 is the sole labeled "
            "detection benchmark here. All other cards are plumbing coverage. "
            "Not clinical validation, not FDA evidence."
        ),
        "limits": {"plumbing_stays": limit, "challenge_stays": challenge_limit},
        "datasets": datasets,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Curie evals on local open datasets")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max stays for unlabeled ICU sets (0 = all; default 50)",
    )
    parser.add_argument(
        "--challenge-limit",
        type=int,
        default=200,
        help="Max Challenge 2019 stays (0 = all; default 200)",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated dataset ids to run",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args(argv)

    if args.probe_only:
        print(json.dumps({"datasets": probe()}, indent=2))
        return 0

    only = {p.strip() for p in args.only.split(",")} if args.only else None
    limit = None if args.limit == 0 else args.limit
    challenge_limit = None if args.challenge_limit == 0 else args.challenge_limit
    report = run_open_suite(limit=limit, challenge_limit=challenge_limit, only=only)
    summary = {
        "disclaimer": report["disclaimer"],
        "limits": report["limits"],
        "datasets": [
            {
                "id": d["id"],
                "status": d.get("status"),
                "metric_family": d.get("metric_family"),
                "metrics": d.get("metrics"),
                "reason": d.get("reason"),
            }
            for d in report["datasets"]
        ],
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.json_out}")
    errors = sum(1 for d in report["datasets"] if d.get("status") == "error")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
