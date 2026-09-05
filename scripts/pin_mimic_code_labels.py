#!/usr/bin/env python3
"""Pin the mimic-code revision + SQL file hashes used for reference labels.

Run on a local checkout of https://github.com/MIT-LCP/mimic-code, then commit
the produced pin JSON deliberately (operator step; never fabricates hashes).

Example::

    python scripts/pin_mimic_code_labels.py --repo ~/src/mimic-code
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.mimic_study.labels import SEPSIS3_SQL_FILES
from eval.mimic_study.labels.pins import pin_from_repo, write_pin


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pin mimic-code label SQL revision")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--git-ref", default="HEAD")
    parser.add_argument(
        "--sql-file",
        action="append",
        default=[],
        metavar="REL/PATH.sql",
        help="additional SQL file (repeatable)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    sql_files = dict(SEPSIS3_SQL_FILES)
    for rel in args.sql_file:
        sql_files[Path(rel).name] = rel
    try:
        pin = pin_from_repo(args.repo, git_ref=args.git_ref, sql_files=sql_files)
        out = write_pin(pin, args.out)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {out}")
    print(json.dumps(pin, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
