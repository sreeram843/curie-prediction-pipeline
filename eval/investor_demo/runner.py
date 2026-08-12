"""CLI for investor demo + claims matrix (CURIE-021)."""

from __future__ import annotations

import argparse
import json

from eval.investor_demo.claims import load_claims_matrix, write_claims_matrix
from eval.investor_demo.scenario import REPORT_PATH, run_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CURIE-021 investor demo")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Replay timeline, chaos checks, write report")
    p_run.add_argument("--no-write", action="store_true")

    sub.add_parser("claims", help="Write/print claims matrix")
    sub.add_parser("show-report", help="Print frozen demo report")

    args = parser.parse_args(argv)

    if args.cmd == "claims":
        path = write_claims_matrix()
        print(json.dumps(load_claims_matrix(path), indent=2))
        print(f"Wrote {path}", file=__import__("sys").stderr)
        return 0

    if args.cmd == "show-report":
        if not REPORT_PATH.is_file():
            print("No report; run: python -m eval.investor_demo.runner run")
            return 1
        print(REPORT_PATH.read_text())
        return 0

    report = run_demo(write=not args.no_write)
    write_claims_matrix()
    print(
        json.dumps(
            {
                "patient_id": report["timeline"]["patient_id"],
                "signals_merged": report["timeline"]["signals_merged"],
                "single_episode": report["timeline"]["single_episode"],
                "volume": report["timeline"]["volume"],
                "chaos_all_passed": report["chaos_all_passed"],
                "wrote": not args.no_write,
                "report_path": str(REPORT_PATH) if not args.no_write else None,
            },
            indent=2,
        )
    )
    return 0 if report["chaos_all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
