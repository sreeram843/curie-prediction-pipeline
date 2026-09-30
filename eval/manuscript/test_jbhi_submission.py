"""Submission-safety checks for the distinct IEEE JBHI manuscript."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEX_PATH = ROOT / "paper" / "jbhi" / "main.tex"
MANIFEST_PATH = ROOT / "eval" / "mimic_study" / "frozen" / "study_manifest.v3.json"
AGGREGATES_PATH = ROOT / "eval" / "mimic_study" / "frozen" / "publication_aggregates.v1.json"
COVER_LETTER_PATH = ROOT / "paper" / "jbhi" / "cover_letter.md"


def _tex() -> str:
    return re.sub(r"\s+", " ", TEX_PATH.read_text())


def _abstract_words(tex: str) -> list[str]:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL)
    assert match, "JBHI abstract is missing"
    plain = re.sub(r"\\[A-Za-z]+(?:\[[^]]*\])?\{([^{}]*)\}", r"\1", match.group(1))
    plain = re.sub(r"\\[A-Za-z]+|[{}$]", " ", plain)
    return re.findall(r"\b[\w.-]+\b", plain)


def test_jbhi_abstract_is_within_250_words() -> None:
    assert len(_abstract_words(_tex())) <= 250


def test_jbhi_has_no_unresolved_inline_markers_or_misleading_terms() -> None:
    tex = _tex().lower()
    for forbidden in ("%author", "todo", "pre-registered", "preregistered", "trustworthy"):
        assert forbidden not in tex


def test_jbhi_has_no_unescaped_percent_that_can_truncate_prose() -> None:
    assert not re.search(r"(?<!\\)%", _tex())


def test_jbhi_scope_is_distinct_and_eicu_is_completeness_only() -> None:
    tex = _tex()
    assert "Locked Alert-Governance Evaluation in MIMIC-IV" in tex
    assert re.search(
        r"eICU-CRD was not\s+used for labeled outcome or governance evaluation", tex
    )
    assert "PhysioNet Challenge 2019" in tex
    assert "does not reuse that cohort" in tex


def test_jbhi_primary_numbers_match_frozen_mimic_manifest() -> None:
    tex = _tex()
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["input_source"]["kind"] == "indexed_stream"
    assert "fixture" not in manifest
    primary = manifest["test_primary"]
    assert f"{primary['stays']:,} stays" in tex
    assert f"{primary['labeled_positive']:,} labeled-positive stays" in tex
    assert f"{100 * primary['governed_sensitivity']:.2f}\\%" in tex
    assert f"{100 * primary['interruptive_sensitivity']:.2f}\\%" in tex
    assert f"{primary['naive_alerts']:,} threshold crossings" in tex
    assert f"{primary['governed_alerts']:,} governed records" in tex
    assert f"{primary['naive_interruptive_alerts']:,} naive interruptive emissions" in tex
    assert f"{primary['interruptive_alerts']:,}" in tex
    assert "Governed interruptive emissions" in tex


def test_jbhi_uses_correct_alert_denominators() -> None:
    tex = _tex()
    manifest = json.loads(MANIFEST_PATH.read_text())
    primary = manifest["test_primary"]
    governed_ratio = primary["governed_alerts"] / primary["naive_alerts"]
    interruptive_ratio = (
        primary["interruptive_alerts"] / primary["naive_interruptive_alerts"]
    )
    assert f"{100 * governed_ratio:.2f}\\%" in tex
    assert f"{100 * interruptive_ratio:.2f}\\%" in tex
    assert "ratio of all governed records to all raw threshold crossings" in tex


def test_jbhi_nna_denominator_is_interruptively_detected_stays() -> None:
    tex = _tex()
    primary = json.loads(MANIFEST_PATH.read_text())["test_primary"]
    reached = round(primary["interruptive_sensitivity"] * primary["labeled_positive"])
    assert primary["interruptive_alerts"] / reached == primary["interruptive_nna"]
    assert f"({reached:,} under full governance)" in tex
    assert "per positive stay reached by an interruption" in tex
    assert "per detected positive stay" not in tex


def test_jbhi_contains_required_disclosures_and_dataset_dois() -> None:
    tex = _tex()
    for required in (
        "Relation to the companion manuscript",
        "Ethics Statement",
        "Acknowledgment",
        "OpenAI Codex",
        "Cursor coding agent",
        "Claude Code",
        "IJMEDI-S-26-06829",
        "10.13026/kpb9-mt58",
        "10.13026/C2WM1R",
    ):
        assert required in tex


def _aggregates() -> dict:
    return json.loads(AGGREGATES_PATH.read_text())


def _pct(value: float) -> str:
    return f"{100 * value:.2f}"


def _ci(stat: dict) -> str:
    return f"{_pct(stat['point'])} ({_pct(stat['lo_2p5'])}--{_pct(stat['hi_97p5'])})"


def test_jbhi_cohort_flow_matches_publication_aggregates() -> None:
    tex = _tex()
    flow = _aggregates()["cohort_flow"]
    splits = flow["split_counts"]
    for value in (
        flow["icustays_source"],
        flow["excluded_later_stay_same_admission"],
        flow["protocol_cohort_stays"],
        splits["outside_protocol_anchor_groups"],
        flow["study_stays_all_splits"],
        splits["development"],
        splits["calibration"],
        splits["test"],
    ):
        assert f"{value:,}" in tex
    recon = flow["reconciliation_with_v1_audit"]
    assert f"{recon['stays_selected_only_under_v2_rule']} stays" in tex
    assert f"{recon['v1_rule_replicated_stays']:,}" in tex


def test_jbhi_characteristics_match_publication_aggregates() -> None:
    tex = _tex()
    chars = _aggregates()["characteristics"]
    for split in ("development", "calibration", "test"):
        c = chars[split]
        age = c["age_years"]
        assert f"{age['median']:.0f} [{age['q1']:.0f}--{age['q3']:.0f}]" in tex
        assert f"{c['female']:,} ({100 * c['female_rate']:.1f})" in tex
        assert f"{c['sepsis3_positive']:,} ({100 * c['sepsis3_rate']:.1f})" in tex
        assert f"{c['patients']:,}" in tex


def test_jbhi_post_hoc_numbers_match_publication_aggregates() -> None:
    tex = _tex()
    post = _aggregates()["test_timing_and_labels"]
    lead = post["lead_time_governed"]
    q = lead["quantiles_hours"]
    assert f"{q['median']:.2f} h" in tex
    assert f"{q['q1']:.2f}--{q['q3']:.2f} h" in tex
    assert f"in {lead['first_alert_after_onset']} stays" in tex
    gated = post["lead_gated_min_2h"]
    assert _ci(gated["governed_sensitivity"]) in tex
    assert _ci(gated["interruptive_sensitivity"]) in tex
    icd = post["icd_label_sensitivity"]
    for count in ("icd_positive", "icd_and_sepsis3", "icd_only", "sepsis3_only"):
        assert f"{icd[count]:,}" in tex
    assert _ci(icd["any_governed_alert_during_stay"]) in tex
    assert _ci(icd["any_interruptive_alert_during_stay"]) in tex
    assert _pct(icd["overlap_primary_window_governed"]) in tex
    assert _pct(icd["overlap_lead_ge_2h_governed"]) in tex
    for group in post["label_negative_alert_rates"].values():
        assert f"{group['stays']:,}" in tex
        assert _pct(group["any_governed_alert"]) in tex
        assert _pct(group["any_interruptive_alert"]) in tex


def test_jbhi_subgroup_rows_match_publication_aggregates() -> None:
    tex = _tex()
    sub = _aggregates()["test_subgroups"]
    labels = {
        ("sex", "female"): "Female",
        ("sex", "male"): "Male",
        ("age_band", "18-44"): "18--44 y",
        ("age_band", "45-64"): "45--64 y",
        ("age_band", "65-79"): "65--79 y",
        ("age_band", "80+"): "$\\geq$80 y",
    }
    for (dim, key), label in labels.items():
        g = sub[dim][key]
        row = " & ".join(
            [
                label,
                f"{g['stays']:,}",
                f"{g['sepsis3_positive']:,}",
                _pct(g["governed_sensitivity"]),
                _pct(g["lead_ge_2h_governed_sensitivity"]),
                _pct(g["interruptive_sensitivity"]),
                f"{g['interruptions_per_100_patient_days']:.1f}",
            ]
        )
        assert row in tex, row


def test_jbhi_ablation_rows_match_publication_aggregates() -> None:
    tex = _tex()
    ablations = _aggregates()["test_ablations"]
    for key in ("threshold_only_naive", "drop_refractory", "drop_page_gate"):
        a = ablations[key]
        assert f"{a['governed_alerts']:,} & {a['interruptive_alerts']:,}" in tex, key


def test_jbhi_graphical_abstract_text_matches_frozen_numbers() -> None:
    text = (ROOT / "paper" / "jbhi" / "graphical_abstract_text.txt").read_text()
    primary = json.loads(MANIFEST_PATH.read_text())["test_primary"]
    lead = _aggregates()["test_timing_and_labels"]["lead_gated_min_2h"]
    assert f"{primary['stays']:,} stays" in text
    assert f"{100 * primary['governed_sensitivity']:.1f}% loose-window detection" in text
    assert f"{100 * primary['interruptive_reduction_ratio']:.1f}% of naive interruptions" in text
    assert f"{100 * lead['governed_sensitivity']['point']:.1f}% of positive stays" in text
    assert f"interruptive precision was {100 * primary['interruptive_precision']:.1f}%" in text


def test_jbhi_cover_letter_has_no_placeholders_and_names_companion() -> None:
    letter = COVER_LETTER_PATH.read_text()
    assert "[INSERT" not in letter
    assert "JAMIA" not in letter
    assert "IJMEDI-S-26-06829" in letter
    assert "Claude Code" in letter
