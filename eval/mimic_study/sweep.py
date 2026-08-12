"""MIMIC-IV operating-point sweep stub (CURIE-014 guardrails).

Full scoring arrives with CURIE-015/016. This module exists so tuning entrypoints
cannot target the locked test split even before the harness lands.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from eval.mimic_study.protocol import (
    ProtocolError,
    assert_split_allowed_for_tuning,
    load_protocol,
    primary_endpoint,
    protocol_summary,
)


def run_sweep(
    *,
    split: str = "development",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Sweep governance knobs on an allowed split only.

    Raises ``ProtocolError`` if ``split`` is the locked test holdout.
    """
    assert_split_allowed_for_tuning(split, command="sweep")
    proto = load_protocol()
    pe = primary_endpoint(proto)
    return {
        "status": "dry_run" if dry_run else "not_implemented",
        "split": split,
        "protocol_id": proto["protocol_id"],
        "primary_endpoint": pe["id"],
        "message": (
            "CURIE-014 guard passed. Full MIMIC sweep requires CURIE-015 harness "
            "and credentialed extract; refusing to invent holdout metrics."
        ),
    }


def run_operating_point_selection(
    *,
    split: str = "calibration",
) -> dict[str, Any]:
    assert_split_allowed_for_tuning(split, command="operating_point_selection")
    return {
        "status": "not_implemented",
        "split": split,
        "message": "Select on calibration only; freeze before touching test.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MIMIC-IV study protocol / sweep guard (CURIE-014)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="Print frozen protocol summary")
    p_show.add_argument("--json", action="store_true")

    p_sweep = sub.add_parser("sweep", help="Sweep (blocked on test split)")
    p_sweep.add_argument(
        "--split",
        default="development",
        help="development | calibration | test (test must fail)",
    )

    p_select = sub.add_parser(
        "select", help="Operating-point selection (blocked on test)"
    )
    p_select.add_argument("--split", default="calibration")

    args = parser.parse_args(argv)

    if args.cmd == "show":
        summary = protocol_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"protocol_id: {summary['protocol_id']}")
            print(f"status: {summary['status']}")
            print(f"primary: {summary['primary_success_rule']}")
            print(f"OPS: {summary['operating_point_rule']}")
            print(f"test forbidden: {summary['test_forbidden_commands']}")
        return 0

    try:
        if args.cmd == "sweep":
            report = run_sweep(split=args.split)
        else:
            report = run_operating_point_selection(split=args.split)
    except ProtocolError as exc:
        print(f"PROTOCOL_VIOLATION: {exc}", flush=True)
        return 2

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
