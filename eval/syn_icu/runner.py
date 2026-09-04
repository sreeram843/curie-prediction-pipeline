"""SYN-ICU synthetic ICU stays → leakage-safe harness run.

Plumbing smoke test only: proves SYN-ICU flows through the same demo-schema
harness as MIMIC-IV demo. Synthetic data — no clinical claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import replay_stay, result_to_public_dict
from ingestion.adapters.syn_icu.convert import convert_syn_icu
from ingestion.adapters.syn_icu.paths import require_syn_icu_dir

RUNNER_VERSION = "0.1.0"


def _report_hash(report: dict[str, Any]) -> str:
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_syn_icu(*, root: Path | None = None, limit: int | None = None) -> dict[str, Any]:
    root = root or require_syn_icu_dir()
    converted = convert_syn_icu(root, limit=limit)
    stays = converted["stays"]

    results = [result_to_public_dict(replay_stay(stay)) for stay in stays]

    signals = sum(len(r["signals"]) for r in results)
    episodes = sum(len(r["episodes"]) for r in results)
    errors = sum(len(r["errors"]) for r in results)
    stays_with_signal = sum(1 for r in results if r["signals"])

    report: dict[str, Any] = {
        "runner_version": RUNNER_VERSION,
        "schema": "syn-icu",
        "dataset_pin": converted["dataset_pin"],
        "coverage": converted["coverage"],
        "warnings": converted["warnings"],
        "stays_scored": len(results),
        "totals": {
            "signals": signals,
            "episodes": episodes,
            "errors": errors,
            "stays_with_signal": stays_with_signal,
        },
        "stays": results,
    }
    report["content_hash"] = _report_hash(
        {k: v for k, v in report.items() if k != "content_hash"}
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score SYN-ICU synthetic stays with Curie rules")
    parser.add_argument("--limit", type=int, default=None, help="Max ICU stays")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_syn_icu(limit=args.limit)
    summary = {
        k: report[k]
        for k in ("runner_version", "schema", "stays_scored", "totals", "warnings", "content_hash")
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
