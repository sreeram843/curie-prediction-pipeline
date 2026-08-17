"""UI-facing benchmark summaries with plain-language explanations.

Loads only frozen aggregate artifacts (no PHI / no stay extracts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


def _load(rel: str) -> dict[str, Any] | None:
    path = REPO / rel
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(x: float | None, digits: int = 1) -> str | None:
    if x is None:
        return None
    return f"{100.0 * float(x):.{digits}f}%"


def _ratio(x: float | None, digits: int = 3) -> str | None:
    if x is None:
        return None
    return f"{float(x):.{digits}f}"


def _hours(x: float | None, digits: int = 2) -> str | None:
    if x is None:
        return None
    return f"{float(x):.{digits}f} h"


def _metric(label: str, value: str | None, explain: str) -> dict[str, str]:
    return {"label": label, "value": value or "—", "explain": explain}


def _challenge_card() -> dict[str, Any]:
    frozen = _load("eval/challenge2019/frozen/p1_setA_winner.json") or {}
    set_a = (frozen.get("setA") or {}).get("metrics") or {}
    det = set_a.get("detection") or {}
    alerts = set_a.get("alerts") or {}
    cohort = set_a.get("cohort") or {}
    knobs = frozen.get("knobs") or {}
    primary_holdout = _load(
        "eval/challenge2019/frozen/holdout_primary_window_m12_p6.v1.json"
    )

    # Lead with primary-window figures when the curated holdout pin exists;
    # otherwise surface setA metrics under the current primary timing freeze.
    if primary_holdout:
        pdet = primary_holdout.get("detection") or {}
        primary_metrics = [
            _metric(
                "Governed sensitivity (window_m12_p6)",
                _pct(pdet.get("governed_sensitivity")),
                (
                    "Primary holdout: share of sepsis-labeled stays with any governed "
                    "alert in [onset−12h, onset+6h]."
                ),
            ),
            _metric(
                "Interruptive sensitivity (emissions)",
                _pct(pdet.get("interruptive_sensitivity")),
                (
                    "Share of sepsis stays with an interruptive emission in-window. "
                    "Emission-level — not episode-arbitrated pages."
                ),
            ),
            _metric(
                "Interruptive NNA (emissions)",
                _ratio(pdet.get("interruptive_nna"), digits=1),
                (
                    "Interruptive emissions per interruptive true-positive stay. "
                    "Not episode-arbitrated pages."
                ),
            ),
            _metric(
                "In-window mean lead hours",
                _hours(pdet.get("mean_lead_hours_in_window")),
                (
                    "Mean hours from first in-window governed alert to label onset "
                    "(window_m12_p6)."
                ),
            ),
        ]
        primary_source = primary_holdout.get("source") or (
            "eval/challenge2019/frozen/holdout_primary_window_m12_p6.v1.json"
        )
    else:
        primary_metrics = [
            _metric(
                "Governed sensitivity (setA · window_m12_p6)",
                _pct(det.get("governed_sensitivity")),
                (
                    "Tuning-split sensitivity under the primary timing freeze. "
                    "Holdout setB primary pin not present yet."
                ),
            ),
            _metric(
                "Interruptive sensitivity (setA emissions)",
                _pct(det.get("interruptive_sensitivity")),
                (
                    "Tuning-split interruptive catch. Emission-level — not "
                    "episode-arbitrated pages."
                ),
            ),
            _metric(
                "Interruptive NNA (setA emissions)",
                _ratio(det.get("interruptive_nna"), digits=1),
                (
                    "Interruptive emissions per interruptive TP on setA. "
                    "Co-primary burden uses reduction ratio."
                ),
            ),
            _metric(
                "Interruptive reduction (setA)",
                _ratio(alerts.get("interruptive_reduction_ratio")),
                (
                    "Tuning-split burden ratio that passed the co-primary gate "
                    "before freezing knobs."
                ),
            ),
        ]
        primary_source = "eval/challenge2019/frozen/p1_setA_winner.json (setA)"

    legacy_holdout = {
        "source": "docs/research/challenge-2019-eval.md · legacy grace≤6h holdout",
        "window_note": (
            "Sensitivity analysis only. Primary detection is window_m12_p6 "
            "(CURIE-004)."
        ),
        "metrics": [
            _metric(
                "Detection sensitivity (legacy grace≤6h)",
                "81.1%",
                (
                    "Legacy published setB figure. Do not quote as the primary "
                    "window_m12_p6 result."
                ),
            ),
            _metric(
                "Interruptive reduction vs naive",
                "0.132 (~7.6× fewer pages)",
                "Legacy holdout burden ratio (goal ≤ 0.25).",
            ),
            _metric(
                "Interruptive NNA (legacy)",
                "~94.2",
                "Legacy pages / interruptive TP under grace≤6h.",
            ),
            _metric(
                "Mean lead hours (unbounded)",
                "~42 h",
                "Unbounded first-alert lead — not in-window lead.",
            ),
        ],
    }

    return {
        "id": "challenge-2019",
        "title": "PhysioNet Challenge 2019 — sepsis alert operating point",
        "tier": "demonstrated",
        "status_label": "Locked retrospective benchmark",
        "what": (
            "Offline replay of Curie SOFA + shared governance against Challenge "
            "SepsisLabel. Tunes on setA, freezes knobs, reports holdout on setB."
        ),
        "how_to_read": (
            "Primary numbers use window_m12_p6. Interruptive metrics are "
            "emission counts unless labeled episode pages. Legacy grace≤6h is "
            "secondary only."
        ),
        "caveats": [
            "Not clinical validation, not FDA evidence, not the official "
            "Challenge utility score.",
            "Partial SOFA inputs and synthetic/Challenge labels — not bedside "
            "outcomes.",
            "Do not retune on training_setB.",
            "Interruptive NNA/sensitivity here are emissions, not "
            "episode-arbitrated pages.",
        ],
        "knobs_summary": knobs.get("description")
        or "persist / crossings / refractory / page gate — see frozen "
        "p1_setA_winner.json",
        "metrics": primary_metrics,
        "metrics_source": primary_source,
        "published_holdout": legacy_holdout,
        "holdout_label": "Legacy sensitivity (grace≤6h)",
        "docs": "docs/research/challenge-2019-eval.md",
        "artifacts": [
            "eval/challenge2019/frozen/p1_setA_winner.json",
            "eval/challenge2019/frozen/timing_primary.v1.json",
            "eval/challenge2019/frozen/holdout_primary_window_m12_p6.v1.json",
            "eval/challenge2019/frozen/miss_analysis.v1.json",
        ],
        "reproduce": (
            "GOV_CONFIG=eval/challenge2019/frozen/p1_setA_winner.json "
            "SET=training_setB LIMIT=0 make challenge-2019"
        ),
        "cohort_note": (
            f"setA stays scored: "
            f"{cohort.get('stays_scored') or frozen.get('setA', {}).get('stays_scored') or '—'}"
        ),
    }


def _investor_card() -> dict[str, Any]:
    report = _load("eval/investor_demo/frozen/demo_report.v1.json") or {}
    vol = (report.get("timeline") or {}).get("volume") or {}
    return {
        "id": "investor-demo",
        "title": "Investor demo — multi-signal → one episode",
        "tier": "demonstrated",
        "status_label": "Synthetic reliability demo",
        "what": (
            "Scripted multi-indicator sequence merged into one patient episode "
            "with chaos checks (duplicate / out-of-order / restart identity)."
        ),
        "how_to_read": (
            "Compare naive alert count to episode interruptive pages. Chaos "
            "passed means identity survived adversarial delivery — not that "
            "outcomes improved."
        ),
        "caveats": [
            report.get("disclaimer") or "Synthetic — not clinical validation.",
            "Volume numbers are scenario-scale, not Challenge n=20k.",
        ],
        "metrics": [
            _metric(
                "Signals → episode",
                f"{report.get('timeline', {}).get('signals_merged', '—')} → 1",
                (
                    "Correlated signals aggregate under the episode arbiter "
                    "instead of paging separately."
                ),
            ),
            _metric(
                "Naive pages",
                str(vol.get("naive_alert_count", "—")),
                "If every emission paged interruptively.",
            ),
            _metric(
                "Episode interruptive pages",
                str(vol.get("episode_interruptive_pages", "—")),
                "Pages after episode arbitration + governance.",
            ),
            _metric(
                "Chaos checks",
                "passed" if report.get("chaos_all_passed") else "failed",
                (
                    "Duplicate delivery, out-of-order events, and restart must "
                    "not corrupt episode identity."
                ),
            ),
        ],
        "docs": "docs/research/claims-matrix.md",
        "artifacts": ["eval/investor_demo/frozen/demo_report.v1.json"],
        "reproduce": "make investor-demo",
    }


def _stewardship_card() -> dict[str, Any]:
    manifest = _load("eval/stewardship/frozen/replay_manifest.v1.json") or {}
    return {
        "id": "stewardship",
        "title": "Alert stewardship — feedback classification (CURIE-024)",
        "tier": "under_evaluation",
        "status_label": "Offline governance analytics",
        "what": (
            "Classifies acknowledgement/dismissal text into a taxonomy and "
            "proposes offline experiments. Never mutates live rules or "
            "thresholds."
        ),
        "how_to_read": (
            "Look for agreement on dual-reviewed fixtures and whether "
            "proposals stay bound to frozen replay manifests. Activation "
            "always requires a human."
        ),
        "caveats": [
            "LLM/stewardship improvement of clinical outcomes is not claimed.",
            "Classifier default is deterministic keyword scoring in this demo.",
            *(manifest.get("forbidden") or []),
        ],
        "metrics": [
            _metric(
                "Mutates active rules",
                "false",
                (
                    "Classifier and proposals are advisory until human "
                    "approval + frozen replay."
                ),
            ),
            _metric(
                "Human approval required",
                str(
                    (manifest.get("activation_policy") or {}).get(
                        "human_approval_required", True
                    )
                ),
                (
                    "No silent promotion of stewardship proposals into "
                    "production knobs."
                ),
            ),
            _metric(
                "Replay binding",
                manifest.get("manifest_id") or "—",
                (
                    "Proposals evaluate against pinned Challenge/MIMIC study "
                    "artifacts only."
                ),
            ),
        ],
        "docs": "docs/governance/alert-stewardship.md",
        "artifacts": [
            "eval/stewardship/frozen/replay_manifest.v1.json",
            "eval/stewardship/fixtures/dual_reviewed.v1.json",
        ],
        "reproduce": "make stewardship",
    }


def _uncertainty_card() -> dict[str, Any]:
    report = _load("eval/uncertainty/frozen/study_report.v1.json") or {}
    base = report.get("baseline_detection") or {}
    after = report.get("after_assist_detection") or {}
    assist = report.get("assistant") or {}
    return {
        "id": "uncertainty-band",
        "title": "Uncertainty-band context assistant (CURIE-025)",
        "tier": "under_evaluation",
        "status_label": "Passive retrospective study",
        "what": (
            "When deterministic evidence is borderline, a grounded assistant "
            "may add context. It must not suppress or escalate alerts."
        ),
        "how_to_read": (
            "Detection metrics before vs after assist should match "
            "(unchanged routing). Judge assistant quality by "
            "unsupported-claim rate and abstention — not by score changes."
        ),
        "caveats": [
            "Fixture-scale study (small n) — not a clinical outcome trial.",
            "Mode is retrospective_passive only.",
        ],
        "metrics": [
            _metric(
                "Detection unchanged",
                str(report.get("detection_unchanged")),
                (
                    "Assistant must not change sensitivity/PPV via routing — "
                    "only add passive context."
                ),
            ),
            _metric(
                "Baseline PPV",
                _pct(base.get("ppv")),
                "Positive predictive value of the deterministic lane before assist.",
            ),
            _metric(
                "After-assist PPV",
                _pct(after.get("ppv")),
                "Should match baseline when detection_unchanged is true.",
            ),
            _metric(
                "Unsupported claim rate",
                _pct(assist.get("unsupported_claim_rate")),
                (
                    "Share of assistant claims lacking allowed evidence IDs — "
                    "must stay near zero."
                ),
            ),
            _metric(
                "Abstention rate",
                _pct(assist.get("abstention_rate")),
                "How often the assistant refuses rather than inventing context.",
            ),
        ],
        "docs": "docs/governance/uncertainty-band.md",
        "artifacts": [
            "eval/uncertainty/frozen/study_report.v1.json",
            "eval/uncertainty/frozen/eligibility_policy.v1.json",
        ],
        "reproduce": "make uncertainty-band",
    }


def _mimic_card() -> dict[str, Any]:
    op = _load("eval/mimic_study/frozen/operating_point.v1.json") or {}
    cal = op.get("calibration") or {}
    return {
        "id": "mimic-study",
        "title": "MIMIC-IV governance study schema (Stage B prep)",
        "tier": "under_evaluation",
        "status_label": "Protocol + demo schema — not Stage B results",
        "what": (
            "Frozen protocol and operating-point schema for a future MIMIC-IV "
            "clinical retrospective under DUA. Current numbers may be "
            "schema/demo scale only."
        ),
        "how_to_read": (
            "Treat this as study design readiness: goals, forbidden splits, "
            "and pin hashes. Do not read calibration demo metrics as clinical "
            "performance."
        ),
        "caveats": [
            "Full MIMIC under DUA is required for Stage B claims.",
            f"Forbidden selection split: {op.get('forbidden_selection_split', 'test')}.",
            "Not claimed as clinical validity in the claims matrix.",
        ],
        "metrics": [
            _metric(
                "Candidate id",
                str(op.get("candidate_id") or "—"),
                "Operating-point identifier selected on development/calibration only.",
            ),
            _metric(
                "Calibration stays (schema)",
                str(cal.get("stays") or "—"),
                "Tiny schema-check cohort — not the locked MIMIC holdout.",
            ),
            _metric(
                "Primary goal",
                str((op.get("goals") or {}).get("primary") or "—"),
                "Sensitivity preservation rule planned for Stage B.",
            ),
            _metric(
                "Co-primary goal",
                str((op.get("goals") or {}).get("coprimary") or "—"),
                "Interruptive burden rule planned for Stage B.",
            ),
        ],
        "docs": "docs/research/mimic-data-sources.md",
        "artifacts": [
            "eval/mimic_study/frozen/protocol.v1.json",
            "eval/mimic_study/frozen/operating_point.v1.json",
        ],
        "reproduce": "make mimic-study",
    }


def _manuscript_card() -> dict[str, Any]:
    man = _load("eval/manuscript/frozen/reproducibility_manifest.v1.json") or {}
    pins = man.get("artifact_pins") or {}
    return {
        "id": "manuscript-package",
        "title": "Manuscript reproducibility package (CURIE-020)",
        "tier": "demonstrated",
        "status_label": "Methods pins + claim tiers",
        "what": (
            "Frozen reproducibility manifest that pins "
            "protocol/operating-point/Challenge hashes and separates "
            "retrospective detection vs unproven outcomes."
        ),
        "how_to_read": (
            "Use for paper methods: git SHA, regenerate command, and which "
            "artifacts are allowed without embedding PHI."
        ),
        "caveats": list((man.get("phi_policy") or {}).get("forbidden") or [])
        or ["Do not commit MIMIC extracts or note text."],
        "metrics": [
            _metric(
                "Package version",
                str(man.get("package_version") or "—"),
                "Manuscript package schema.",
            ),
            _metric(
                "Git SHA (pinned)",
                str(man.get("git_sha") or "—")[:12],
                "Code revision recorded at freeze.",
            ),
            _metric(
                "Pinned artifacts",
                str(len(pins)),
                "Count of hashed study artifacts listed in the manifest.",
            ),
        ],
        "docs": "docs/research/manuscript-package.md",
        "artifacts": ["eval/manuscript/frozen/reproducibility_manifest.v1.json"],
        "reproduce": "make manuscript",
    }


def build_benchmarks_summary() -> dict[str, Any]:
    cards = [
        _challenge_card(),
        _investor_card(),
        _manuscript_card(),
        _stewardship_card(),
        _uncertainty_card(),
        _mimic_card(),
    ]
    return {
        "schema_version": "1.0.0",
        "title": "Curie benchmarks",
        "disclaimer": (
            "These are engineering and retrospective offline benchmarks. "
            "They are not clinical validation, FDA clearance, or proof of "
            "outcome improvement."
        ),
        "how_to_use_this_page": [
            "Start with Challenge 2019 primary window_m12_p6 metrics.",
            "Treat legacy grace≤6h holdout as sensitivity analysis only.",
            "Use Investor demo for episode arbitration + chaos at demo scale.",
            (
                "Treat stewardship / uncertainty / MIMIC cards as under "
                "evaluation unless the claims matrix says demonstrated."
            ),
            "Every card lists caveats — read those before quoting externally.",
        ],
        "benchmarks": cards,
    }
