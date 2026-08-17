"""Research manuscript package builder (CURIE-020).

Assembles methods pins, claim tiers, tables, and figure specs from frozen
evaluation artifacts. Never reads or embeds PhysioNet MIMIC patient extracts.
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

PACKAGE_VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUT = Path(__file__).resolve().parent / "frozen"
GENERATED_OUT = Path(__file__).resolve().parent / "generated"

# Paths relative to repo root — public, non-PHI artifacts only.
ARTIFACT_PATHS = {
    "mimic_protocol": "eval/mimic_study/frozen/protocol.v1.json",
    "mimic_operating_point": "eval/mimic_study/frozen/operating_point.v1.json",
    "mimic_study_manifest": "eval/mimic_study/frozen/study_manifest.v1.json",
    "mimic_harness_fixture": "eval/fixtures/mimic_harness/demo_schema_stays.v1.json",
    "challenge_operating_point": "eval/challenge2019/frozen/p1_setA_winner.json",
    "challenge_timing": "eval/challenge2019/frozen/timing_primary.v1.json",
    "challenge_bundle_sha": "eval/challenge2019/frozen/sepsis-sofa.challenge2019-p1.v1.sha256",
    "challenge_bundle": "eval/challenge2019/frozen/sepsis-sofa.challenge2019-p1.v1.json",
}

# Forbidden in committed manuscript artifacts (PHI / extract leakage).
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
    return json.loads((ROOT / rel).read_text())


def artifact_pins() -> dict[str, Any]:
    pins: dict[str, Any] = {}
    for key, rel in ARTIFACT_PATHS.items():
        path = ROOT / rel
        if not path.is_file():
            pins[key] = {"path": rel, "present": False}
            continue
        entry: dict[str, Any] = {
            "path": rel,
            "present": True,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    for k in (
                        "protocol_id",
                        "schema_version",
                        "study_version",
                        "manifest_version",
                        "timing_id",
                        "candidate_id",
                        "name",
                    ):
                        if k in data:
                            entry[k] = data[k]
            except json.JSONDecodeError:
                entry["json_ok"] = False
        elif path.suffix == ".sha256":
            entry["digest_file_contents"] = path.read_text().strip()[:80]
        pins[key] = entry
    return pins


def claim_tiers() -> dict[str, Any]:
    return {
        "retrospective_detection": {
            "status": "demonstrated_on_public_or_demo_artifacts",
            "includes": [
                "Challenge 2019 offline detection sensitivity vs SepsisLabel (setA tune / setB holdout)",  # noqa: E501
                "Demo-schema MIMIC harness PE-1 plumbing (not Stage B clinical results)",
                "Deterministic SOFA / governance / episode contracts via golden fixtures",
            ],
            "does_not_include": [
                "Prospective clinical outcomes",
                "Mortality or length-of-stay improvement",
            ],
        },
        "alert_policy_utility": {
            "status": "demonstrated_as_burden_metrics",
            "includes": [
                "Interruptive reduction ratio vs naive thresholding (Challenge holdout + demo study)",  # noqa: E501
                "Ablation of governance knobs on demo-schema fixtures",
                "Passive vs interruptive lane separation (page gate)",
            ],
            "does_not_include": [
                "Clinician workflow acceptance",
                "Dismiss-rate improvement in live EHR",
            ],
        },
        "clinical_outcome_effects": {
            "status": "not_claimed",
            "includes": [],
            "does_not_include": [
                "Reduced mortality, organ failure, or time-to-antibiotics",
                "Diagnosis of sepsis/AKI",
                "FDA clearance / SaMD validation",
                "Superiority to NEWS/qSOFA/vendor CDS",
            ],
        },
    }


def cohort_flow() -> dict[str, Any]:
    """Logical cohort flow from protocol — aggregate counts only where frozen."""
    protocol = load_json(ARTIFACT_PATHS["mimic_protocol"])
    challenge = load_json(ARTIFACT_PATHS["challenge_operating_point"])
    mimic_manifest = load_json(ARTIFACT_PATHS["mimic_study_manifest"])
    set_a = (challenge.get("setA") or {}).get("metrics", {}).get("cohort", {})
    temporal = protocol.get("splits") or {}
    split_roles = {}
    for key in ("development", "calibration", "test"):
        v = temporal.get(key)
        if isinstance(v, dict):
            split_roles[key] = {
                "role": v.get("role"),
                "intime_range": v.get("intime_range"),
            }
    return {
        "challenge2019": {
            "source": "PhysioNet Challenge 2019 training archives (ODbL; local data/ gitignored)",
            "tune_split": "training_setA",
            "holdout_split": "training_setB",
            "setA_stays_scored": set_a.get("stays_scored")
            or challenge.get("setA", {}).get("stays_scored"),
            "setA_sepsis_stays": set_a.get("sepsis_stays"),
            "setA_non_sepsis_stays": set_a.get("non_sepsis_stays"),
            "holdout_stays_documented": 20000,
            "note": "Holdout outputs are not committed; cite docs/research/challenge-2019-eval.md",
        },
        "mimic_iv_protocol": {
            "protocol_id": protocol.get("protocol_id"),
            "planned_unit": "ICU stay",
            "splits": split_roles
            or {
                "development": "2008–2016",
                "calibration": "2017–2018",
                "test": "2019 (evaluate once)",
            },
            "stage_b_status": "protocol frozen; full extract not committed",
        },
        "mimic_demo_schema_study": {
            "fixture": ARTIFACT_PATHS["mimic_harness_fixture"],
            "test_stays": (mimic_manifest.get("test_primary") or {}).get("stays"),
            "dataset_pin": mimic_manifest.get("dataset_pin"),
            "note": "Plumbing / leakage-safe harness only — not clinical Stage B",
        },
    }


def ablation_table() -> list[dict[str, Any]]:
    manifest = load_json(ARTIFACT_PATHS["mimic_study_manifest"])
    rows: list[dict[str, Any]] = []
    primary = manifest.get("test_primary") or {}
    rows.append(
        {
            "ablation_id": "primary_operating_point",
            "governed_sensitivity": primary.get("governed_sensitivity"),
            "interruptive_sensitivity": primary.get("interruptive_sensitivity"),
            "interruptive_reduction_ratio": primary.get("interruptive_reduction_ratio"),
            "interruptive_nna": primary.get("interruptive_nna"),
            "mean_in_window_lead_hours": primary.get("mean_in_window_lead_hours"),
            "meets_pe1": primary.get("meets_pe1"),
            "meets_pe2": primary.get("meets_pe2"),
        }
    )
    for aid, summary in sorted((manifest.get("test_ablations") or {}).items()):
        rows.append(
            {
                "ablation_id": aid,
                "governed_sensitivity": summary.get("governed_sensitivity"),
                "interruptive_sensitivity": summary.get("interruptive_sensitivity"),
                "interruptive_reduction_ratio": summary.get("interruptive_reduction_ratio"),
                "interruptive_nna": summary.get("interruptive_nna"),
                "mean_in_window_lead_hours": summary.get("mean_in_window_lead_hours"),
                "meets_pe1": summary.get("meets_pe1"),
                "meets_pe2": summary.get("meets_pe2"),
            }
        )
    return rows


def operating_point_pareto() -> list[dict[str, Any]]:
    """Sensitivity vs interruptive burden candidates (selection, not test peek)."""
    op = load_json(ARTIFACT_PATHS["mimic_operating_point"])
    points = []
    for c in op.get("candidates_scored") or []:
        points.append(
            {
                "candidate_id": c.get("candidate_id"),
                "governed_sensitivity": c.get("governed_sensitivity"),
                "interruptive_reduction_ratio": c.get("interruptive_reduction_ratio"),
                "meets_pe1": c.get("meets_pe1"),
                "selected": c.get("candidate_id") == op.get("candidate_id"),
                "split": "calibration",
            }
        )
    challenge = load_json(ARTIFACT_PATHS["challenge_operating_point"])
    set_a = challenge.get("setA") or {}
    metrics = set_a.get("metrics") or {}
    det = metrics.get("detection") or {}
    alerts = metrics.get("alerts") or {}
    points.append(
        {
            "candidate_id": challenge.get("candidate_id") or challenge.get("name"),
            "governed_sensitivity": det.get("governed_sensitivity"),
            "interruptive_reduction_ratio": alerts.get("interruptive_reduction_ratio"),
            "meets_pe1": set_a.get("meets_primary"),
            "selected": True,
            "split": "challenge_setA",
        }
    )
    return points


def timing_figure_spec() -> dict[str, Any]:
    timing = load_json(ARTIFACT_PATHS["challenge_timing"])
    challenge = load_json(ARTIFACT_PATHS["challenge_operating_point"])
    det = ((challenge.get("setA") or {}).get("metrics") or {}).get("detection") or {}
    mimic = load_json(ARTIFACT_PATHS["mimic_study_manifest"]).get("test_primary") or {}
    return {
        "primary_window": timing.get("primary_detection"),
        "timing_classes": timing.get("timing_classes"),
        "challenge_setA_mean_lead_hours": {
            "naive": det.get("mean_lead_hours_naive"),
            "governed": det.get("mean_lead_hours_governed"),
            "interruptive": det.get("mean_lead_hours_interruptive"),
            "note": "Unbounded first-alert lead on setA; primary paper window is window_m12_p6",
        },
        "mimic_demo_mean_in_window_lead_hours": mimic.get("mean_in_window_lead_hours"),
    }


def calibration_figure_spec() -> dict[str, Any]:
    op = load_json(ARTIFACT_PATHS["mimic_operating_point"])
    return {
        "source": "mimic demo-schema operating-point selection",
        "selected_candidate": op.get("candidate_id"),
        "calibration_summary": op.get("calibration"),
        "goals": op.get("goals"),
        "note": (
            "Not probability calibration (Brier/reliability). "
            "Shows operating-point selection metrics on the calibration split only."
        ),
    }


def subgroup_table() -> list[dict[str, Any]]:
    """Planned subgroups from protocol — counts filled only when frozen aggregates exist."""
    return [
        {
            "subgroup": "Challenge sepsis-labeled stays (setA)",
            "status": "aggregate_only",
            "n": ((load_json(ARTIFACT_PATHS["challenge_operating_point"]).get("setA") or {})
                  .get("metrics") or {})
            .get("cohort", {})
            .get("sepsis_stays"),
            "claim_tier": "retrospective_detection",
        },
        {
            "subgroup": "Challenge non-sepsis stays (setA)",
            "status": "aggregate_only",
            "n": ((load_json(ARTIFACT_PATHS["challenge_operating_point"]).get("setA") or {})
                  .get("metrics") or {})
            .get("cohort", {})
            .get("non_sepsis_stays"),
            "claim_tier": "alert_policy_utility",
        },
        {
            "subgroup": "MIMIC-IV comfort care / ESRD / OR transfer",
            "status": "protocol_planned_stage_b",
            "n": None,
            "claim_tier": "not_yet_evaluated",
        },
        {
            "subgroup": "Partial completeness stays (demo study test)",
            "status": "demo_schema",
            "n": (load_json(ARTIFACT_PATHS["mimic_study_manifest"]).get("test_primary") or {}).get(
                "partial_completeness_stays"
            ),
            "claim_tier": "retrospective_detection",
        },
    ]


def failure_analysis() -> dict[str, Any]:
    return {
        "known_failure_modes": [
            {
                "id": "FN-partial-sofa",
                "description": "Challenge hourly fields lack full SOFA components; scores are partial.",  # noqa: E501
                "mitigation": "Report completeness; fail closed on missing critical inputs in streaming path.",  # noqa: E501
            },
            {
                "id": "FN-label-semantics",
                "description": "Challenge SepsisLabel starts ~6h before clinical onset; lead time can look optimistic.",  # noqa: E501
                "mitigation": "Frozen timing_primary.v1 treats onset as label_start; window_m12_p6 primary.",  # noqa: E501
            },
            {
                "id": "FN-page-gate",
                "description": "Interruptive sensitivity < governed sensitivity when page gate is strict.",  # noqa: E501
                "mitigation": "Separate detection (any emit) from burden (interruptive); dual-lane reporting.",  # noqa: E501
            },
            {
                "id": "FN-demo-schema-n",
                "description": "Demo MIMIC fixtures are tiny; PE-2 may fail; not Stage B evidence.",
                "mitigation": "Label demo results as plumbing; Stage B requires PhysioNet extract under DUA.",  # noqa: E501
            },
            {
                "id": "FP-watch-volume",
                "description": "Governed watch lane preserves sensitivity but can keep high all-alert NNA.",  # noqa: E501
                "mitigation": "Primary burden metric is interruptive reduction, not all-alert volume.",  # noqa: E501
            },
        ],
        "claim_boundary": (
            "Failures above affect retrospective detection and alert-policy metrics only. "
            "They do not license clinical-outcome claims."
        ),
    }


def build_manifest() -> dict[str, Any]:
    pins = artifact_pins()
    body = {
        "manifest_version": "1.0.0",
        "package_version": PACKAGE_VERSION,
        "curie_ticket": "CURIE-020",
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha(),
        "regenerate_command": "make manuscript",
        "module": "python -m eval.manuscript.package build",
        "phi_policy": {
            "commits_patient_level_mimic": False,
            "allowed": [
                "Aggregate metrics",
                "Protocol / operating-point / fixture hashes",
                "Public Challenge aggregate stats already in frozen JSON",
            ],
            "forbidden": [
                "MIMIC row extracts",
                "hadm_id / subject_id lists",
                "Note text / PHI",
                "Local data/archive stay files",
            ],
        },
        "artifact_pins": pins,
        "claim_tiers": claim_tiers(),
        "cohort_flow": cohort_flow(),
        "methods_pins": {
            "protocol_doc": "docs/research/mimic-iv-study-protocol.md",
            "challenge_eval_doc": "docs/research/challenge-2019-eval.md",
            "clinical_validation_doc": "docs/research/clinical-validation.md",
            "manuscript_doc": "docs/research/manuscript-package.md",
            "rule_selection": "Forbidden on temporal test / Challenge setB",
        },
    }
    # Stable hash excludes generated_at / git_sha volatility for content checks
    stable = {k: v for k, v in body.items() if k not in {"generated_at", "git_sha"}}
    body["content_hash"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True, default=str).encode()
    ).hexdigest()
    return body


def render_markdown_tables(manifest: dict[str, Any]) -> str:
    lines = [
        "# Generated manuscript tables (CURIE-020)",
        "",
        f"_Regenerated by `make manuscript`. Package {manifest['package_version']}._",
        "",
        "## Claim tiers",
        "",
    ]
    for tier, data in (manifest.get("claim_tiers") or {}).items():
        lines.append(f"### `{tier}` — **{data.get('status')}**")
        lines.append("")
        for item in data.get("includes") or []:
            lines.append(f"- Includes: {item}")
        for item in data.get("does_not_include") or []:
            lines.append(f"- Excludes: {item}")
        lines.append("")

    lines.extend(["## Ablation table (demo-schema test)", ""])
    lines.append(
        "| Ablation | Gov sens | Int sens | Int reduction | Int NNA | Lead (h) | PE-1 | PE-2 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---|---|")
    for row in ablation_table():
        lines.append(
            "| {ablation_id} | {governed_sensitivity} | {interruptive_sensitivity} | "
            "{interruptive_reduction_ratio} | {interruptive_nna} | {mean_in_window_lead_hours} | "
            "{meets_pe1} | {meets_pe2} |".format(**{k: row.get(k) for k in row})
        )
    lines.append("")

    lines.extend(["## Operating-point / Pareto candidates", ""])
    lines.append("| Candidate | Split | Gov sens | Int reduction | Selected |")
    lines.append("|---|---|---:|---:|---|")
    for p in operating_point_pareto():
        lines.append(
            f"| {p.get('candidate_id')} | {p.get('split')} | {p.get('governed_sensitivity')} | "
            f"{p.get('interruptive_reduction_ratio')} | {p.get('selected')} |"
        )
    lines.append("")

    lines.extend(["## Subgroups", ""])
    lines.append("| Subgroup | Status | n | Claim tier |")
    lines.append("|---|---|---:|---|")
    for s in subgroup_table():
        lines.append(
            f"| {s['subgroup']} | {s['status']} | {s['n']} | {s['claim_tier']} |"
        )
    lines.append("")

    lines.extend(["## Failure analysis", ""])
    for fm in failure_analysis()["known_failure_modes"]:
        lines.append(f"- **{fm['id']}:** {fm['description']} → _{fm['mitigation']}_")
    lines.append("")
    lines.append(failure_analysis()["claim_boundary"])
    lines.append("")
    return "\n".join(lines)


def render_figure_specs() -> dict[str, Any]:
    return {
        "cohort_flow_mermaid": """flowchart TD
  A[PhysioNet Challenge 2019 archives] --> B[setA tune]
  B --> C[Freeze operating point]
  C --> D[setB holdout once]
  E[MIMIC-IV protocol v1] --> F[development sweep]
  F --> G[calibration select]
  G --> H[test evaluate once]
  I[Demo-schema fixtures] --> J[Harness + ablation plumbing]
  J -.->|not Stage B| H
  style I fill:#eee
  style J fill:#eee
""",
        "pareto": operating_point_pareto(),
        "timing": timing_figure_spec(),
        "calibration": calibration_figure_spec(),
    }


def scan_for_phi(text: str) -> list[str]:
    hits: list[str] = []
    for pat in _PHI_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


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
        (frozen_dir / "reproducibility_manifest.v1.json").write_text(manifest_text)
        (generated_dir / "tables.md").write_text(tables_md)
        (generated_dir / "figure_specs.v1.json").write_text(figures_json)

    return {
        "manifest": manifest,
        "tables_md": tables_md,
        "figures": figures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CURIE-020 manuscript package")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_build = sub.add_parser("build", help="Write manifest + generated tables/figures")
    p_build.add_argument("--no-write", action="store_true")
    sub.add_parser("show-manifest", help="Print frozen reproducibility manifest")
    sub.add_parser("phi-scan", help="Scan frozen/generated outputs for PHI-like patterns")

    args = parser.parse_args(argv)
    if args.cmd == "show-manifest":
        path = FROZEN_OUT / "reproducibility_manifest.v1.json"
        if not path.is_file():
            print("No manifest; run: python -m eval.manuscript.package build")
            return 1
        print(path.read_text())
        return 0

    if args.cmd == "phi-scan":
        ok = True
        for path in [
            FROZEN_OUT / "reproducibility_manifest.v1.json",
            GENERATED_OUT / "tables.md",
            GENERATED_OUT / "figure_specs.v1.json",
            ROOT / "docs" / "manuscript-package.md",
        ]:
            if not path.is_file():
                continue
            hits = scan_for_phi(path.read_text())
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
                "artifacts_pinned": sum(
                    1
                    for v in result["manifest"]["artifact_pins"].values()
                    if v.get("present")
                ),
                "wrote": not args.no_write,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
