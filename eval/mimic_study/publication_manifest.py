"""Create a publication-safe successor to the frozen Stage B v2 manifest.

The v2 numerical result is immutable, but two legacy metadata fields identify
the demo runner rather than the indexed full-cohort runner that produced it.
This module creates a new version that records the correction and preserves
all numerical sections byte-for-byte at the JSON-object level.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from eval.mimic_harness.replay import stable_report_hash

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
SOURCE_PATH = FROZEN_DIR / "study_manifest.v2.json"
OUTPUT_PATH = FROZEN_DIR / "study_manifest.v3.json"
EXPECTED_SOURCE_HASH = "5faf68dc4627a2c284871e8e1382b3e4fc5e4d0ef88bfc690d1397b4da5e28be"
NUMERICAL_SECTIONS = (
    "test_primary",
    "test_ablations",
    "bootstrap_ci",
    "miss_analysis_summary",
)


def _verified_source(path: Path = SOURCE_PATH) -> dict[str, Any]:
    source = json.loads(path.read_text())
    body = {key: value for key, value in source.items() if key != "content_hash"}
    actual = stable_report_hash(body)
    recorded = source.get("content_hash")
    if actual != recorded or recorded != EXPECTED_SOURCE_HASH:
        raise ValueError(
            "refusing provenance repair: frozen v2 content hash does not match the "
            f"reviewed source ({recorded=}, {actual=})"
        )
    return source


def build_publication_manifest(source: dict[str, Any]) -> dict[str, Any]:
    """Return a provenance-corrected manifest without changing study metrics."""
    output = copy.deepcopy(source)
    output.pop("content_hash", None)
    output.pop("fixture", None)
    output.update(
        {
            "manifest_version": "2.0.0",
            "study_version": "0.2.1",
            "regenerate_command": "make mimic-study-v2-full WRITE_FROZEN=1",
            "module": "python scripts/run_curie_041_stage_b.py",
            "source_manifest": {
                "path": "eval/mimic_study/frozen/study_manifest.v2.json",
                "content_hash": EXPECTED_SOURCE_HASH,
                "change_scope": "provenance metadata only; numerical sections unchanged",
            },
            "input_source": {
                "kind": "indexed_stream",
                "dataset_pin": copy.deepcopy(source["dataset_pin"]),
                "index_hash": source["index_hash"],
                "labels_content_hash": source["labels_content_hash"],
            },
        }
    )
    for section in NUMERICAL_SECTIONS:
        if output[section] != source[section]:
            raise AssertionError(f"numerical section changed during repair: {section}")
    output["content_hash"] = stable_report_hash(output)
    return output


def write_publication_manifest(
    *, source_path: Path = SOURCE_PATH, output_path: Path = OUTPUT_PATH
) -> dict[str, Any]:
    source = _verified_source(source_path)
    output = build_publication_manifest(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2) + "\n")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    output = write_publication_manifest(source_path=args.source, output_path=args.output)
    print(json.dumps({"path": str(args.output), "content_hash": output["content_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

