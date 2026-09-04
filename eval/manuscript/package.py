"""Challenge 2019 retrospective alert-governance manuscript package.

The package has one results dataset: PhysioNet Challenge 2019. Other adapters,
demo-schema studies, golden fixtures, and parity checks are methods or appendix
evidence only and never contribute sensitivity or clinical-effect estimates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PACKAGE_VERSION = "2.0.0"
MANIFEST_FILENAME = "reproducibility_manifest.v2.json"
FIGURE_SPECS_FILENAME = "figure_specs.v2.json"
ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUT = Path(__file__).resolve().parent / "frozen"
GENERATED_OUT = Path(__file__).resolve().parent / "generated"

RESULT_ARTIFACT_PATHS = {
    "challenge_operating_point": "eval/challenge2019/frozen/p1_setA_winner.json",
    "challenge_holdout_primary": (
        "eval/challenge2019/frozen/holdout_primary_window_m12_p6.v1.json"
    ),
    "challenge_holdout_primary_ci": (
        "eval/challenge2019/frozen/holdout_primary_window_m12_p6.v2.json"
    ),
    "challenge_timing": "eval/challenge2019/frozen/timing_primary.v1.json",
    "challenge_robustness": "eval/challenge2019/frozen/robustness_summary.v1.json",
    "challenge_comparators": (
        "eval/challenge2019/frozen/comparators_setB_window_m12_p6.v1.json"
    ),
    "challenge_ablation": (
        "eval/challenge2019/frozen/ablation_setB_window_m12_p6.v1.json"
    ),
    "challenge_miss_v2": "eval/challenge2019/frozen/miss_analysis.v2.json",
    "challenge_pareto": "eval/challenge2019/frozen/pareto_named_profiles.v1.json",
    "challenge_bundle_sha": (
        "eval/challenge2019/frozen/sepsis-sofa.challenge2019-p1.v1.sha256"
    ),
    "challenge_bundle": (
        "eval/challenge2019/frozen/sepsis-sofa.challenge2019-p1.v1.json"
    ),
}

APPENDIX_ARTIFACT_PATHS = {
    "sofa_golden_fixtures": "eval/fixtures/golden/sofa_cases.v0.2.json",
    "cross_runtime_parity": "eval/fixtures/golden/cross_runtime_parity.v1.json",
    "governance_parity": "eval/fixtures/golden/governance_parity.v1.json",
    "leakage_harness_fixture": (
        "eval/fixtures/mimic_harness/demo_schema_stays.v1.json"
    ),
}

ARTIFACT_PATHS = {**RESULT_ARTIFACT_PATHS, **APPENDIX_ARTIFACT_PATHS}

PAPER_PATH = "paper/DRAFT.md"
PACKAGE_DOC_PATH = "paper/REPRODUCIBILITY.md"

# Forbidden in committed manuscript artifacts (PHI / local extract leakage).
_PHI_PATTERNS = [
    re.compile(r"\bhadm_id\s*[:=]\s*\d+", re.I),
    re.compile(r"\bsubject_id\s*[:=]\s*\d+", re.I),
    re.compile(r"\bstay_id\s*[:=]\s*\d+", re.I),
    re.compile(r"data/mimic[\w\-./]*", re.I),
    re.compile(r"physionet\.org/files", re.I),
    re.compile(r"/files/mimiciv/", re.I),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def load_json(rel: str) -> dict[str, Any]:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def artifact_pins() -> dict[str, Any]:
    pins: dict[str, Any] = {}
    for key, rel in ARTIFACT_PATHS.items():
        path = ROOT / rel
        tier = "result" if key in RESULT_ARTIFACT_PATHS else "methods_appendix"
        if not path.is_file():
            pins[key] = {"path": rel, "present": False, "role": tier}
            continue
        entry: dict[str, Any] = {
            "path": rel,
            "present": True,
            "role": tier,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for field in (
                    "schema_version",
                    "timing_id",
                    "candidate_id",
                    "name",
                    "id",
                ):
                    if field in data:
                        entry[field] = data[field]
        elif path.suffix == ".sha256":
            entry["digest_file_contents"] = path.read_text(encoding="utf-8").strip()
        pins[key] = entry
    return pins


def claim_tiers() -> dict[str, Any]:
    return {
        "retrospective_detection": {
            "status": "demonstrated_on_frozen_public_challenge_holdout",
            "dataset": "physionet-challenge-2019",
            "includes": [
                "Governed sensitivity against Challenge SepsisLabel on setB",
                "Interruptive-emission sensitivity and NNA on setB",
                "In-window lead time under frozen window_m12_p6",
            ],
            "does_not_include": [
                "Sepsis diagnosis",
                "MIMIC-IV or external-site validation",
                "Prospective clinical performance",
            ],
        },
        "alert_policy_utility": {
            "status": "demonstrated_retrospectively",
            "dataset": "physionet-challenge-2019",
            "includes": [
                "SetA interruptive-emission reduction versus threshold-only SOFA",
                "Frozen setA-to-setB operating-point evaluation",
                "Secondary timing-definition robustness on setB",
                "SetB ablation of frozen governance knobs (no reselection)",
                "Hourly SIRS / NEWS2 / qSOFA comparators on the Challenge window",
            ],
            "does_not_include": [
                "Delivered clinician pages",
                "Workflow adoption or alert acceptance",
                "Improved patient outcomes",
            ],
        },
        "clinical_outcome_effects": {
            "status": "not_claimed",
            "dataset": None,
            "includes": [],
            "does_not_include": [
                "Reduced mortality, organ failure, or treatment delay",
                "Clinical validation",
                "FDA clearance or SaMD authorization",
                "Superiority to NEWS, qSOFA, or commercial CDS",
            ],
        },
    }


def cohort_flow() -> dict[str, Any]:
    selected = load_json(RESULT_ARTIFACT_PATHS["challenge_operating_point"])
    set_a = selected.get("setA") or {}
    metrics = set_a.get("metrics") or {}
    cohort = metrics.get("cohort") or {}
    holdout = load_json(RESULT_ARTIFACT_PATHS["challenge_holdout_primary"])
    return {
        "dataset": "PhysioNet Challenge 2019 v1.0.0",
        "selection": {
            "split": "training_setA",
            "n_stays": cohort.get("stays_scored") or set_a.get("stays_scored"),
            "sepsis_label_positive_stays": cohort.get("sepsis_stays"),
            "sepsis_label_negative_stays": cohort.get("non_sepsis_stays"),
            "role": "tune_and_freeze",
        },
        "holdout": {
            "split": "training_setB",
            "n_stays": holdout.get("n_stays"),
            "role": "primary_holdout_quote_once",
        },
        "other_datasets": {
            "role": "methods_and_adapter_coverage_only",
            "names": [
                "MIMIC-IV demo",
                "eICU demo",
                "MIMIC-IV FHIR demo",
                "SYN-ICU",
                "Synthea",
            ],
            "results_metrics_allowed": False,
        },
    }


def challenge_results() -> dict[str, Any]:
    selected = load_json(RESULT_ARTIFACT_PATHS["challenge_operating_point"])
    set_a = selected.get("setA") or {}
    metrics = set_a.get("metrics") or {}
    cohort = metrics.get("cohort") or {}
    alerts = metrics.get("alerts") or {}
    detection = metrics.get("detection") or {}

    holdout = load_json(RESULT_ARTIFACT_PATHS["challenge_holdout_primary"])
    holdout_detection = holdout.get("detection") or {}
    holdout_ci = load_json(RESULT_ARTIFACT_PATHS["challenge_holdout_primary_ci"])
    return {
        "setA": {
            "role": "selection",
            "n_stays": cohort.get("stays_scored") or set_a.get("stays_scored"),
            "sepsis_label_positive_stays": cohort.get("sepsis_stays"),
            "naive_emissions": alerts.get("naive_total"),
            "governed_emissions": alerts.get("governed_total"),
            "interruptive_emissions": alerts.get("interruptive_total"),
            "governed_sensitivity": detection.get("governed_sensitivity"),
            "interruptive_sensitivity": detection.get("interruptive_sensitivity"),
            "interruptive_reduction_ratio": alerts.get(
                "interruptive_reduction_ratio"
            ),
            "candidate_id": selected.get("candidate_id"),
            "knobs": selected.get("knobs") or {},
        },
        "setB": {
            "role": "primary_holdout",
            "n_stays": holdout.get("n_stays"),
            "detection_mode_id": holdout.get("detection_mode_id"),
            "governed_sensitivity": holdout_detection.get("governed_sensitivity"),
            "interruptive_sensitivity": holdout_detection.get(
                "interruptive_sensitivity"
            ),
            "interruptive_nna": holdout_detection.get("interruptive_nna"),
            "mean_lead_hours_in_window": holdout_detection.get(
                "mean_lead_hours_in_window"
            ),
            "bootstrap": (holdout_ci.get("bootstrap") or {}),
            "unit_note": (
                "Interruptive metrics are emissions, not episode-arbitrated or "
                "clinician-delivered pages."
            ),
        },
    }


def robustness_table() -> list[dict[str, Any]]:
    artifact = load_json(RESULT_ARTIFACT_PATHS["challenge_robustness"])
    return [
        {
            **row,
            "role": artifact.get("role", "sensitivity_analysis"),
            "ranking_stable": artifact.get("ranking_stable"),
        }
        for row in artifact.get("modes") or []
    ]


def operating_point_figure_spec() -> dict[str, Any]:
    pareto = load_json(RESULT_ARTIFACT_PATHS["challenge_pareto"])
    return {
        "title": "Named profiles plus frozen winner (setA, window_m12_p6)",
        "x": "interruptive_reduction_ratio",
        "y": "governed_sensitivity",
        "points": pareto.get("points") or [],
        "note": (
            pareto.get("notes") or [""]
        )[0],
    }


def timing_figure_spec() -> dict[str, Any]:
    timing = load_json(RESULT_ARTIFACT_PATHS["challenge_timing"])
    set_b = challenge_results()["setB"]
    return {
        "title": "Primary setB timing window",
        "label_start_semantics": (timing.get("label_semantics") or {}).get("note"),
        "primary_window": timing.get("primary_detection"),
        "holdout": {
            "n_stays": set_b["n_stays"],
            "governed_sensitivity": set_b["governed_sensitivity"],
            "mean_lead_hours_in_window": set_b["mean_lead_hours_in_window"],
        },
    }


def appendix_evidence() -> list[dict[str, str]]:
    return [
        {
            "artifact": "Golden SOFA fixtures",
            "path": APPENDIX_ARTIFACT_PATHS["sofa_golden_fixtures"],
            "role": "Deterministic scorer boundary checks; not a results cohort",
        },
        {
            "artifact": "Python/Java parity fixtures",
            "path": APPENDIX_ARTIFACT_PATHS["cross_runtime_parity"],
            "role": "Cross-runtime implementation check; not clinical validation",
        },
        {
            "artifact": "Governance parity fixtures",
            "path": APPENDIX_ARTIFACT_PATHS["governance_parity"],
            "role": "Policy-decision parity check; not a results cohort",
        },
        {
            "artifact": "Demo-schema leakage harness",
            "path": APPENDIX_ARTIFACT_PATHS["leakage_harness_fixture"],
            "role": "Availability-time and ablation plumbing only; no sensitivity estimate",
        },
    ]


def failure_analysis() -> list[dict[str, str]]:
    return [
        {
            "id": "partial-sofa",
            "limitation": (
                "Challenge data lack GCS, urine output, vasopressor-dose ladders, "
                "and a reliable mechanical-ventilation flag."
            ),
            "paper_handling": "Call the computed score partial SOFA throughout.",
        },
        {
            "id": "proxy-label",
            "limitation": (
                "SepsisLabel is shifted approximately six hours before the "
                "Challenge clinical-onset definition."
            ),
            "paper_handling": (
                "Use label_start, freeze window_m12_p6, and report 5.97 h as "
                "label-relative lead time."
            ),
        },
        {
            "id": "emissions-not-pages",
            "limitation": (
                "Interruptive counts are emission-level page candidates, not "
                "episode-arbitrated or delivered clinician pages."
            ),
            "paper_handling": "Use 'interruptive emissions' in methods and results.",
        },
        {
            "id": "single-public-challenge",
            "limitation": "setB is a holdout within Challenge 2019, not an external site.",
            "paper_handling": (
                "Do not claim MIMIC-IV, prospective, multisite, or clinical validation."
            ),
        },
    ]


def build_manifest() -> dict[str, Any]:
    body = {
        "manifest_version": "2.0.0",
        "package_version": PACKAGE_VERSION,
        "curie_ticket": "CURIE-020",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "regenerate_command": "make manuscript",
        "module": "python -m eval.manuscript.package build",
        "supported_claim": (
            "Shared governance reduces interruptive emissions versus threshold-only "
            "partial SOFA while preserving retrospective Challenge SepsisLabel "
            "detection under a frozen setA-to-setB evaluation."
        ),
        "result_scope": {
            "dataset": "physionet-challenge-2019",
            "version": "1.0.0",
            "selection_split": "training_setA",
            "holdout_split": "training_setB",
            "other_datasets_are_results": False,
        },
        "phi_policy": {
            "commits_patient_level_data": False,
            "allowed": [
                "Aggregate Challenge metrics",
                "Rule, timing, fixture, and reproducibility hashes",
                "Public methods and synthetic implementation checks",
            ],
            "forbidden": [
                "Patient-level extracts or identifiers",
                "Local Challenge row files",
                "MIMIC row extracts or note text",
            ],
        },
        "artifact_pins": artifact_pins(),
        "claim_tiers": claim_tiers(),
        "cohort_flow": cohort_flow(),
        "results": challenge_results(),
        "methods_pins": {
            "paper_doc": PAPER_PATH,
            "package_doc": PACKAGE_DOC_PATH,
            "challenge_eval_doc": "docs/research/challenge-2019-eval.md",
            "architecture_doc": "docs/architecture.md",
            "rule_selection": "Tune on setA; never tune or reselect on setB",
            "primary_timing": "window_m12_p6",
        },
    }
    stable = {
        key: value
        for key, value in body.items()
        if key not in {"generated_at", "git_sha"}
    }
    body["content_hash"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True, default=str).encode()
    ).hexdigest()
    return body


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def render_markdown_tables(manifest: dict[str, Any]) -> str:
    results = manifest["results"]
    set_a = results["setA"]
    set_b = results["setB"]
    lines = [
        "# Generated Challenge 2019 manuscript tables",
        "",
        f"_Regenerated by `make manuscript`. Package {manifest['package_version']}._",
        "",
        "> One results dataset: PhysioNet Challenge 2019. All fixtures and demo adapters are",
        "> methods or appendix evidence only.",
        "",
        "## Table 1. Study splits",
        "",
        "| Split | Stays | Role |",
        "|---|---:|---|",
        f"| training_setA | {set_a['n_stays']} | Tune and freeze operating point |",
        f"| training_setB | {set_b['n_stays']} | Primary holdout; quote once |",
        "",
        "## Table 2. Frozen setA operating point",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Governed sensitivity | {_pct(set_a['governed_sensitivity'])} |",
        f"| Interruptive sensitivity | {_pct(set_a['interruptive_sensitivity'])} |",
        (
            "| Interruptive reduction ratio vs threshold-only | "
            f"{set_a['interruptive_reduction_ratio']:.3f} |"
        ),
        f"| Threshold-only emissions | {set_a['naive_emissions']} |",
        f"| Interruptive emissions | {set_a['interruptive_emissions']} |",
        "",
        "## Table 3. Primary setB holdout (`window_m12_p6`)",
        "",
        "| Metric | Value | Unit / denominator |",
        "|---|---:|---|",
        (
            f"| Governed sensitivity | {_pct(set_b['governed_sensitivity'])} | "
            "Labeled-positive stays with any governed emission in-window |"
        ),
        (
            f"| Interruptive sensitivity | {_pct(set_b['interruptive_sensitivity'])} | "
            "Labeled-positive stays with an interruptive emission in-window |"
        ),
        (
            f"| Interruptive NNA | {set_b['interruptive_nna']:.1f} | "
            "Interruptive emissions per interruptive true-positive stay |"
        ),
        (
            f"| In-window mean lead | {set_b['mean_lead_hours_in_window']:.2f} h | "
            "First governed emission to label_start |"
        ),
        "",
        "## Table 4. Secondary timing robustness on setB",
        "",
        "| Detection definition | Naive sensitivity | Governed sensitivity | Role |",
        "|---|---:|---:|---|",
    ]
    for row in robustness_table():
        lines.append(
            f"| {row['detection_mode_id']} | {_pct(row['naive_sensitivity'])} | "
            f"{_pct(row['governed_sensitivity'])} | sensitivity analysis |"
        )
    lines.extend(
        [
            "",
            "> The legacy `grace_6` value of 81.1% is not the primary result.",
            "",
            "## Table 5. SetB bedside comparators (`window_m12_p6`)",
            "",
            "| Policy | Sensitivity | Emissions | NNA |",
            "|---|---:|---:|---:|",
        ]
    )
    comparators = load_json(RESULT_ARTIFACT_PATHS["challenge_comparators"])
    for card in comparators.get("comparators") or []:
        m = card.get("metrics") or {}
        nna = m.get("nna")
        nna_s = "—" if nna is None else f"{nna:.1f}"
        lines.append(
            f"| {card.get('title')} | {_pct(m.get('sensitivity'))} | "
            f"{m.get('emissions')} | {nna_s} |"
        )
    lines.extend(
        [
            "",
            "> Incomplete NEWS2 (no AVPU) and partial qSOFA (no GCS). Not a superiority claim.",
            "",
            "## Table 6. SetB ablation of the frozen winner",
            "",
            "| Variant | Gov sens | Int sens | Int reduction | Int NNA |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    ablation = load_json(RESULT_ARTIFACT_PATHS["challenge_ablation"])
    for row in ablation.get("variants") or []:
        nna = row.get("interruptive_nna")
        nna_s = "—" if nna is None else f"{nna:.1f}"
        red = row.get("interruptive_reduction_ratio")
        red_s = "—" if red is None else f"{red:.3f}"
        lines.append(
            f"| {row.get('id')} | {_pct(row.get('governed_sensitivity'))} | "
            f"{_pct(row.get('interruptive_sensitivity'))} | {red_s} | {nna_s} |"
        )
    lines.extend(
        [
            "",
            "## Appendix A. Methods and implementation evidence",
            "",
            "| Artifact | Role in paper |",
            "|---|---|",
        ]
    )
    for row in appendix_evidence():
        lines.append(f"| {row['artifact']} | {row['role']} |")
    lines.extend(["", "## Limitations required in every submission", ""])
    for item in failure_analysis():
        lines.append(
            f"- **{item['id']}:** {item['limitation']} {item['paper_handling']}"
        )
    lines.append("")
    return "\n".join(lines)


def render_figure_specs() -> dict[str, Any]:
    return {
        "architecture_mermaid": """flowchart LR
  A[Clinical events] --> B[Kafka]
  B --> C[Flink deterministic partial SOFA]
  R[Versioned rule bundle] --> C
  C --> G[Shared governance]
  G --> W[Passive watch emission]
  G --> P[Interruptive emission]
  P -. post-alert only .-> L[Optional LLM narrative]
""",
        "cohort_flow_mermaid": """flowchart LR
  A[Challenge setA: 20,336 stays] --> B[Tune governance]
  B --> C[Freeze p1_setA_winner]
  C --> D[Challenge setB: 20,000 stays]
  D --> E[Primary window_m12_p6 results]
""",
        "operating_point": operating_point_figure_spec(),
        "timing": timing_figure_spec(),
        "robustness": {
            "title": "SetB detection-definition robustness",
            "rows": robustness_table(),
            "primary_result_not_in_series": (
                "window_m12_p6 governed sensitivity = 79.5%"
            ),
            "note": "The 81.1% grace_6 result is secondary, not primary.",
        },
    }


def scan_for_phi(text: str) -> list[str]:
    return [pattern.pattern for pattern in _PHI_PATTERNS if pattern.search(text)]


def build(
    *,
    write: bool = True,
    frozen_out: Path | None = None,
    generated_out: Path | None = None,
) -> dict[str, Any]:
    manifest = build_manifest()
    tables_md = render_markdown_tables(manifest)
    figures = render_figure_specs()
    figures_json = json.dumps(figures, indent=2, default=str) + "\n"
    manifest_text = json.dumps(manifest, indent=2, default=str) + "\n"

    for label, blob in (
        ("manifest", manifest_text),
        ("tables", tables_md),
        ("figures", figures_json),
    ):
        hits = scan_for_phi(blob)
        if hits:
            raise RuntimeError(f"PHI-like patterns in {label}: {hits}")

    if write:
        frozen_dir = frozen_out or FROZEN_OUT
        generated_dir = generated_out or GENERATED_OUT
        frozen_dir.mkdir(parents=True, exist_ok=True)
        generated_dir.mkdir(parents=True, exist_ok=True)
        (frozen_dir / MANIFEST_FILENAME).write_text(manifest_text, encoding="utf-8")
        (generated_dir / "tables.md").write_text(tables_md, encoding="utf-8")
        (generated_dir / FIGURE_SPECS_FILENAME).write_text(
            figures_json,
            encoding="utf-8",
        )
        if frozen_out is None and generated_out is None:
            from eval.manuscript.generate_paper_tables import write_all

            write_all()

    return {"manifest": manifest, "tables_md": tables_md, "figures": figures}


def _scan_paths() -> list[Path]:
    return [
        FROZEN_OUT / MANIFEST_FILENAME,
        GENERATED_OUT / "tables.md",
        GENERATED_OUT / FIGURE_SPECS_FILENAME,
        ROOT / PACKAGE_DOC_PATH,
        ROOT / PAPER_PATH,
        ROOT / "paper" / "main.tex",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Challenge 2019 manuscript package")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="Write manifest and generated tables/figures")
    p_build.add_argument("--no-write", action="store_true")
    sub.add_parser("show-manifest", help="Print the frozen reproducibility manifest")
    sub.add_parser("phi-scan", help="Scan manuscript outputs for PHI-like patterns")
    args = parser.parse_args(argv)

    if args.cmd == "show-manifest":
        path = FROZEN_OUT / MANIFEST_FILENAME
        if not path.is_file():
            print("No v2 manifest; run: python -m eval.manuscript.package build")
            return 1
        print(path.read_text(encoding="utf-8"))
        return 0

    if args.cmd == "phi-scan":
        ok = True
        for path in _scan_paths():
            if not path.is_file():
                continue
            hits = scan_for_phi(path.read_text(encoding="utf-8"))
            if hits:
                ok = False
                print(f"FAIL {path}: {hits}")
            else:
                print(f"OK {path.relative_to(ROOT)}")
        return 0 if ok else 2

    result = build(write=not args.no_write)
    print(
        json.dumps(
            {
                "package_version": PACKAGE_VERSION,
                "git_sha": result["manifest"]["git_sha"],
                "content_hash": result["manifest"]["content_hash"],
                "result_artifacts_pinned": sum(
                    1
                    for value in result["manifest"]["artifact_pins"].values()
                    if value.get("present") and value.get("role") == "result"
                ),
                "wrote": not args.no_write,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
