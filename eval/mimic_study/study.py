"""Locked MIMIC ablation + robustness study runner (CURIE-016).

Threshold / operating-point selection uses development + calibration only.
The temporal test split is evaluated once for the primary result and ablations.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import FIXTURES_DIR, stable_report_hash
from eval.mimic_study.ablations import (
    ABLATION_KNOBS,
    FULL_GOVERNANCE_KNOBS,
    SELECTION_CANDIDATES,
)
from eval.mimic_study.metrics import summarize_cohort
from eval.mimic_study.protocol import (
    ProtocolError,
    assert_command_allowed_on_split,
    assert_split_allowed_for_tuning,
    load_protocol,
)
from eval.mimic_study.study_replay import replay_stay_ablation

STUDY_VERSION = "0.1.0"
FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
OPERATING_POINT_PATH = FROZEN_DIR / "operating_point.v1.json"
MANIFEST_PATH = FROZEN_DIR / "study_manifest.v1.json"


def _load_stays(fixtures_dir: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = fixtures_dir or FIXTURES_DIR
    path = root / "demo_schema_stays.v1.json"
    data = json.loads(path.read_text())
    return list(data.get("stays") or []), data


def _stays_for_split(stays: list[dict[str, Any]], split_id: str) -> list[dict[str, Any]]:
    return [s for s in stays if str(s.get("split_id") or "") == split_id]


def evaluate_knobs_on_split(
    stays: list[dict[str, Any]],
    knobs: dict[str, Any] | None,
    *,
    split_id: str,
) -> dict[str, Any]:
    rows = [
        replay_stay_ablation(stay, knobs=knobs)
        for stay in _stays_for_split(stays, split_id)
    ]
    summary = summarize_cohort(rows)
    summary["split_id"] = split_id
    return {"summary": summary, "stays": rows}


def select_operating_point(
    stays: list[dict[str, Any]],
    *,
    candidates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """OPS-1: tune candidates on development metrics context; select on calibration."""
    assert_split_allowed_for_tuning("development", command="sweep")
    assert_split_allowed_for_tuning("calibration", command="operating_point_selection")
    # Explicitly refuse test
    try:
        assert_command_allowed_on_split("test", "operating_point_selection")
        raise AssertionError("test must forbid operating_point_selection")
    except ProtocolError:
        pass

    cand = candidates or SELECTION_CANDIDATES
    scored: list[dict[str, Any]] = []
    for cid, knobs in cand.items():
        # Development is allowed for sweep; we record it but select on calibration.
        evaluate_knobs_on_split(stays, knobs, split_id="development")
        cal = evaluate_knobs_on_split(stays, knobs, split_id="calibration")
        summary = cal["summary"]
        scored.append(
            {
                "candidate_id": cid,
                "knobs": knobs,
                "calibration": summary,
                "meets_pe1": bool(summary.get("meets_pe1")),
                "interruptive_reduction_ratio": summary.get(
                    "interruptive_reduction_ratio"
                ),
                "governed_sensitivity": summary.get("governed_sensitivity"),
                "interruptive_nna": summary.get("interruptive_nna"),
            }
        )

    eligible = [c for c in scored if c["meets_pe1"]]
    pool = eligible or scored

    def _sort_key(c: dict[str, Any]) -> tuple:
        red = c["interruptive_reduction_ratio"]
        red_key = red if red is not None else 1.0
        nna = c["interruptive_nna"]
        nna_key = nna if nna is not None else 1e9
        sens = c["governed_sensitivity"]
        sens_key = -(sens if sens is not None else -1.0)
        return (red_key, nna_key, sens_key, c["candidate_id"])

    pool.sort(key=_sort_key)
    winner = pool[0]
    freeze = {
        "name": "mimic_demo_schema_operating_point",
        "schema_version": "1.0.0",
        "study_version": STUDY_VERSION,
        "protocol_id": load_protocol()["protocol_id"],
        "candidate_id": winner["candidate_id"],
        "selected_at": datetime.now(UTC).isoformat(),
        "source_splits": ["development", "calibration"],
        "forbidden_selection_split": "test",
        "goals": {
            "primary": load_protocol()["primary_endpoint"]["success_rule"],
            "coprimary": load_protocol()["coprimary_endpoint"]["success_rule"],
        },
        "calibration": winner["calibration"],
        "knobs": winner["knobs"],
        "candidates_scored": [
            {
                "candidate_id": c["candidate_id"],
                "meets_pe1": c["meets_pe1"],
                "interruptive_reduction_ratio": c["interruptive_reduction_ratio"],
                "governed_sensitivity": c["governed_sensitivity"],
            }
            for c in scored
        ],
    }
    return freeze


def run_ablations_on_test(
    stays: list[dict[str, Any]],
    *,
    primary_knobs: dict[str, Any],
) -> dict[str, Any]:
    """Execute each pre-specified ablation once on the locked test split."""
    assert_command_allowed_on_split("test", "locked_ablation_eval")
    tables: dict[str, Any] = {}
    for ablation_id, knobs in ABLATION_KNOBS.items():
        use_knobs = primary_knobs if ablation_id == "full_governance" else knobs
        if ablation_id == "full_governance":
            use_knobs = primary_knobs
        result = evaluate_knobs_on_split(stays, use_knobs, split_id="test")
        tables[ablation_id] = result["summary"]
    return tables


def run_primary_on_test(
    stays: list[dict[str, Any]],
    knobs: dict[str, Any],
) -> dict[str, Any]:
    assert_command_allowed_on_split("test", "locked_primary_eval")
    return evaluate_knobs_on_split(stays, knobs, split_id="test")


def build_manifest(
    *,
    operating_point: dict[str, Any],
    primary_test: dict[str, Any],
    ablations: dict[str, Any],
    fixture_meta: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "manifest_version": "1.0.0",
        "study_version": STUDY_VERSION,
        "protocol_id": load_protocol()["protocol_id"],
        "regenerate_command": "make mimic-study",
        "module": "python -m eval.mimic_study.study run",
        "fixture": "eval/fixtures/mimic_harness/demo_schema_stays.v1.json",
        "dataset_pin": fixture_meta.get("dataset_pin"),
        "operating_point_path": "eval/mimic_study/frozen/operating_point.v1.json",
        "selection_splits": ["development", "calibration"],
        "primary_eval_split": "test",
        "primary_eval_once": True,
        "ablations": sorted(ABLATION_KNOBS.keys()),
        "operating_point_candidate": operating_point.get("candidate_id"),
        "test_primary": primary_test.get("summary"),
        "test_ablations": ablations,
    }
    body["content_hash"] = stable_report_hash(
        {k: v for k, v in body.items() if k != "content_hash"}
    )
    return body


def run_study(
    *,
    fixtures_dir: Path | None = None,
    write_frozen: bool = True,
) -> dict[str, Any]:
    stays, fixture_meta = _load_stays(fixtures_dir)
    operating_point = select_operating_point(stays)
    knobs = operating_point["knobs"]
    primary = run_primary_on_test(stays, knobs)
    ablations = run_ablations_on_test(stays, primary_knobs=knobs)
    # Robustness: also report threshold-only on test for PE comparison
    naive = evaluate_knobs_on_split(stays, None, split_id="test")

    report = {
        "study_version": STUDY_VERSION,
        "protocol_id": load_protocol()["protocol_id"],
        "operating_point": {
            "candidate_id": operating_point["candidate_id"],
            "knobs": knobs,
            "calibration": operating_point["calibration"],
        },
        "selection_guard": {
            "tuned_on": ["development", "calibration"],
            "test_used_for_selection": False,
        },
        "primary_test": primary["summary"],
        "naive_test": naive["summary"],
        "ablations_test": ablations,
        "fixture_schema_version": fixture_meta.get("schema_version"),
    }
    report["content_hash"] = stable_report_hash(
        {k: v for k, v in report.items() if k != "content_hash"}
    )
    manifest = build_manifest(
        operating_point=operating_point,
        primary_test=primary,
        ablations=ablations,
        fixture_meta=fixture_meta,
    )

    if write_frozen:
        FROZEN_DIR.mkdir(parents=True, exist_ok=True)
        # Strip volatile selected_at from hash-stable OP file? Keep it but tests
        # compare candidate_id / knobs.
        OPERATING_POINT_PATH.write_text(json.dumps(operating_point, indent=2) + "\n")
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    return {"report": report, "manifest": manifest, "operating_point": operating_point}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MIMIC demo-schema ablation study (CURIE-016)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="Select on cal, evaluate test once, write manifest")
    p_run.add_argument("--fixtures-dir", type=Path, default=None)
    p_run.add_argument("--json-out", type=Path, default=None)
    p_run.add_argument("--no-write", action="store_true")

    p_show = sub.add_parser("show-manifest", help="Print frozen study manifest")
    p_guard = sub.add_parser(
        "guard-test", help="Demonstrate that selection on test is forbidden"
    )

    args = parser.parse_args(argv)

    if args.cmd == "show-manifest":
        if not MANIFEST_PATH.is_file():
            print("No frozen manifest; run: python -m eval.mimic_study.study run")
            return 1
        print(MANIFEST_PATH.read_text())
        return 0

    if args.cmd == "guard-test":
        try:
            assert_split_allowed_for_tuning("test", command="sweep")
        except ProtocolError as exc:
            print(f"PROTOCOL_VIOLATION (expected): {exc}")
            return 0
        print("ERROR: test sweep was allowed")
        return 1

    result = run_study(
        fixtures_dir=args.fixtures_dir,
        write_frozen=not args.no_write,
    )
    report = result["report"]
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2))
        print(f"Wrote {args.json_out}")
    print(
        json.dumps(
            {
                "study_version": report["study_version"],
                "candidate_id": report["operating_point"]["candidate_id"],
                "test_meets_pe1": report["primary_test"].get("meets_pe1"),
                "test_meets_pe2": report["primary_test"].get("meets_pe2"),
                "ablations": sorted(report["ablations_test"].keys()),
                "content_hash": report["content_hash"],
                "manifest_hash": result["manifest"]["content_hash"],
                "selection_used_test": report["selection_guard"]["test_used_for_selection"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
