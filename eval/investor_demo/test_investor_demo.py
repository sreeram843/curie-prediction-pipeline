"""CURIE-021 investor demo + claims matrix tests."""

from __future__ import annotations

from pathlib import Path

from eval.investor_demo.claims import claims_matrix, write_claims_matrix
from eval.investor_demo.scenario import run_demo


def test_claims_matrix_categories(tmp_path: Path) -> None:
    matrix = claims_matrix()
    assert set(matrix["by_status"]) == {
        "demonstrated",
        "under_evaluation",
        "not_claimed",
    }
    statuses = {c["status"] for c in matrix["claims"]}
    assert statuses == {"demonstrated", "under_evaluation", "not_claimed"}
    # Hard non-claims required by backlog
    not_claimed_ids = set(matrix["by_status"]["not_claimed"])
    assert "DX-SEPSIS" in not_claimed_ids
    assert "OUTCOME-MORT" in not_claimed_ids
    assert "CLIN-VALID" in not_claimed_ids
    assert "REG-CLEAR" in not_claimed_ids
    assert "RELIABILITY" in set(matrix["by_status"]["under_evaluation"])
    write_claims_matrix(tmp_path / "claims_matrix.v1.json")


def test_investor_demo_timeline_and_chaos(tmp_path: Path) -> None:
    report = run_demo(
        write=True,
        report_path=tmp_path / "demo_report.v1.json",
        db_path=tmp_path / "demo.sqlite",
    )
    assert report["timeline"]["single_episode"] is True
    assert report["timeline"]["signals_merged"] >= 3
    vol = report["timeline"]["volume"]
    assert vol["naive_alert_count"] > vol["episode_interruptive_pages"]
    assert vol["governed_passive_count"] >= 1
    assert report["chaos_all_passed"] is True
    assert report["chaos"]["restart"].get("episode_ids_stable") is True
    assert all(row["rule_bundle_hash"] for row in report["evidence_and_hashes"])
    assert all(row["evidence_ids"] for row in report["evidence_and_hashes"])
    assert (tmp_path / "demo_report.v1.json").is_file()
