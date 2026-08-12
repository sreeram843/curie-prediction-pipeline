"""CLI for alert stewardship feedback classification (CURIE-024)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.stewardship.classifier import (
    FeedbackRecord,
    aggregate_classifications,
    agreement_metrics,
    classify_record,
)
from eval.stewardship.proposals import (
    PROPOSALS_PATH,
    approve_proposal,
    assert_no_active_rule_mutation,
    build_proposals,
    evaluate_proposal_against_manifest,
)
from eval.stewardship.taxonomy import taxonomy_public

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dual_reviewed.v1.json"


def _load_records(path: Path) -> list[FeedbackRecord]:
    raw = json.loads(path.read_text())
    return [FeedbackRecord.model_validate(row) for row in raw]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CURIE-024 stewardship")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Classify dual-reviewed fixtures + proposals")
    p_run.add_argument("--fixtures", type=Path, default=FIXTURES)
    p_run.add_argument("--write", action="store_true")

    p_eval = sub.add_parser(
        "evaluate-proposals", help="Bind proposals to frozen replay manifest"
    )
    p_eval.add_argument("--proposals", type=Path, default=PROPOSALS_PATH)

    p_approve = sub.add_parser("approve", help="Human-approve a proposal (no rule mutation)")
    p_approve.add_argument("--proposal-id", required=True)
    p_approve.add_argument("--approved-by", required=True)
    p_approve.add_argument("--proposals", type=Path, default=PROPOSALS_PATH)

    sub.add_parser("taxonomy", help="Print taxonomy")

    args = parser.parse_args(argv)

    if args.cmd == "taxonomy":
        print(json.dumps(taxonomy_public(), indent=2))
        return 0

    if args.cmd == "run":
        records = _load_records(args.fixtures)
        preds = [classify_record(r) for r in records]
        metrics = agreement_metrics(records, preds)
        aggregates = aggregate_classifications(records, preds)
        proposals = build_proposals(records, preds)
        for p in proposals:
            assert_no_active_rule_mutation(p)
            bind = evaluate_proposal_against_manifest(p)
            if not bind["ok"]:
                print(json.dumps(bind, indent=2))
                return 2
        report = {
            "metrics": metrics,
            "aggregates": aggregates,
            "proposals": [p.model_dump(mode="json") for p in proposals],
            "mutates_active_rules": False,
        }
        if args.write:
            PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            PROPOSALS_PATH.write_text(json.dumps(report["proposals"], indent=2) + "\n")
        print(json.dumps(report, indent=2, default=str))
        return 0

    if args.cmd == "evaluate-proposals":
        if not args.proposals.is_file():
            print("No proposals file; run: python -m eval.stewardship.runner run --write")
            return 1
        proposals = [
            __import__("eval.stewardship.proposals", fromlist=["ExperimentProposal"])
            .ExperimentProposal.model_validate(row)
            for row in json.loads(args.proposals.read_text())
        ]
        results = [evaluate_proposal_against_manifest(p) for p in proposals]
        print(json.dumps(results, indent=2))
        return 0 if all(r["ok"] for r in results) else 2

    if args.cmd == "approve":
        rows = json.loads(args.proposals.read_text())
        from eval.stewardship.proposals import ExperimentProposal

        updated = []
        found = False
        for row in rows:
            prop = ExperimentProposal.model_validate(row)
            if prop.proposal_id == args.proposal_id:
                prop = approve_proposal(prop, approved_by=args.approved_by)
                assert_no_active_rule_mutation(prop)
                found = True
            updated.append(prop.model_dump(mode="json"))
        if not found:
            print(f"proposal not found: {args.proposal_id}")
            return 1
        args.proposals.write_text(json.dumps(updated, indent=2) + "\n")
        print(json.dumps({"approved": args.proposal_id, "mutates_active_rules": False}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
