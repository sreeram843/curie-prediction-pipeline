"""CLI for uncertainty-band study (CURIE-025)."""

from __future__ import annotations

import argparse
import json

from eval.uncertainty.policy import write_policy
from eval.uncertainty.study import REPORT_PATH, run_study


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CURIE-025 uncertainty-band study")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="Run retrospective passive study")
    p_run.add_argument("--no-write", action="store_true")
    sub.add_parser("show-report", help="Print frozen study report")
    sub.add_parser("write-policy", help="Write frozen eligibility policy")

    args = parser.parse_args(argv)
    if args.cmd == "write-policy":
        path = write_policy()
        print(f"Wrote {path}")
        return 0
    if args.cmd == "show-report":
        if not REPORT_PATH.is_file():
            print("No report; run: python -m eval.uncertainty.runner run")
            return 1
        print(REPORT_PATH.read_text())
        return 0

    report = run_study(write=not args.no_write)
    print(
        json.dumps(
            {
                "policy_id": report["policy_id"],
                "detection_unchanged": report["detection_unchanged"],
                "sensitivity": report["baseline_detection"]["sensitivity"],
                "ppv": report["baseline_detection"]["ppv"],
                "alert_burden_total": report["baseline_detection"]["alert_burden_total"],
                "unsupported_claim_rate": report["assistant"]["unsupported_claim_rate"],
                "abstention_rate": report["assistant"]["abstention_rate"],
                "safety": report["safety"],
                "wrote": not args.no_write,
            },
            indent=2,
        )
    )
    ok = (
        report["detection_unchanged"]
        and report["safety"]["routing_unchanged_all"]
        and report["safety"]["interruptive_depends_on_llm"] is False
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
