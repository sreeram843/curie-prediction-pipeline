"""Validate shared trusted-fact fixtures (CURIE-022)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from ingestion.bridge.gate import admit_trusted_fact

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_manifest(manifest_path: Path | None = None) -> int:
    path = manifest_path or (FIXTURES / "manifest.v1.json")
    manifest = json.loads(path.read_text())
    root = path.parent
    failed = 0
    for case in manifest["cases"]:
        payload = json.loads((root / case["file"]).read_text())
        clock = None
        if case.get("clock"):
            clock = datetime.fromisoformat(case["clock"].replace("Z", "+00:00"))
        decision = admit_trusted_fact(payload, clock=clock)
        ok = (
            decision.outcome == case["expect_outcome"]
            and decision.may_mutate_scoring is case["may_mutate_scoring"]
        )
        status = "OK" if ok else "FAIL"
        print(
            f"{status} {case['id']}: outcome={decision.outcome} "
            f"scoring={decision.may_mutate_scoring} reason={decision.reason}"
        )
        if not ok:
            failed += 1
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CURIE-022 trusted-fact fixtures")
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args(argv)
    return run_manifest(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
