"""CLI for the MIMIC leakage-safe harness (CURIE-015)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.mimic_harness.replay import run_demo_schema_harness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MIMIC-IV demo-schema leakage-safe timeline harness (CURIE-015)"
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=None,
        help="Directory containing demo_schema_stays.v1.json",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_demo_schema_harness(fixtures_dir=args.fixtures_dir)
    text = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text)
        print(f"Wrote {args.json_out}")
    print(
        json.dumps(
            {
                "harness_version": report["harness_version"],
                "stays_scored": report["stays_scored"],
                "content_hash": report["content_hash"],
                "code_pins": report["code_pins"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
