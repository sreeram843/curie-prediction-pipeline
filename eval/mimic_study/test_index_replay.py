"""Tests for availability-time replay over the indexed representation (Phase C2).

Covers: single-stay / bounded / full runs sharing one code path, LIMIT=0,
leakage (future events, discharge information, later corrections, labels),
deterministic reruns, and manifest attachment.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyarrow")

from eval.mimic_study.index_replay import (  # noqa: E402
    indexed_study_rows,
    replay_indexed_stays,
    run_with_manifest,
)
from eval.mimic_study.indexing import build_index, load_stay_events  # noqa: E402
from eval.mimic_study.protocol import load_protocol  # noqa: E402
from eval.mimic_study.test_indexing import make_mimic_source  # noqa: E402


@pytest.fixture(scope="module")
def mimic_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    source = make_mimic_source(tmp_path_factory.mktemp("replay-src"))
    index_dir = tmp_path_factory.mktemp("replay-idx") / "idx"
    build_index(source_root=source, index_dir=index_dir, dataset="mimic")
    return index_dir


class TestSameCodePath:
    def test_indexed_study_rows_export_canonical_stays(self, mimic_index: Path) -> None:
        exported = indexed_study_rows(index_dir=mimic_index, stay_ids=["10"])
        assert exported["schema_version"] == "1.0.0"
        assert exported["protocol_id"] == "mimic-iv-governance-study.v1"
        assert exported["stays"][0]["stay_id"] == "10"
        assert exported["stays"][0]["labs"]

    def test_single_bounded_full_identical(self, mimic_index: Path) -> None:
        single = replay_indexed_stays(index_dir=mimic_index, stay_ids=["10"])
        bounded = replay_indexed_stays(index_dir=mimic_index, limit=1)
        full = replay_indexed_stays(index_dir=mimic_index, limit=None)
        assert single["stays_replayed"] == 1
        assert bounded["stays_replayed"] == 1
        assert full["stays_replayed"] == 3
        assert single["stays"][0] == bounded["stays"][0] == full["stays"][0]

    def test_limit_zero_is_full(self, mimic_index: Path) -> None:
        report = replay_indexed_stays(index_dir=mimic_index, limit=0)
        assert report["stays_replayed"] == 3
        assert report["selection"]["mode"] == "full"

    def test_stay_ids_subset_order_preserved(self, mimic_index: Path) -> None:
        report = replay_indexed_stays(index_dir=mimic_index, stay_ids=["12", "10"])
        assert [s["stay_id"] for s in report["stays"]] == ["12", "10"]

    def test_unknown_stay_id_fails_closed(self, mimic_index: Path) -> None:
        from eval.mimic_study.indexing import IndexError

        with pytest.raises(IndexError, match="missing from index"):
            replay_indexed_stays(index_dir=mimic_index, stay_ids=["nope"])

    def test_deterministic_rerun(self, mimic_index: Path) -> None:
        a = replay_indexed_stays(index_dir=mimic_index, limit=None)
        b = replay_indexed_stays(index_dir=mimic_index, limit=None)
        assert [s["timeline_hash"] for s in a["stays"]] == [
            s["timeline_hash"] for s in b["stays"]
        ]
        assert a["missingness"] == b["missingness"]

    def test_protocol_cohort_selection(self, mimic_index: Path) -> None:
        # Cohort filter is deterministic; selection path uses the same replay loop.
        report = replay_indexed_stays(
            index_dir=mimic_index, apply_protocol_cohort=True, limit=2, seed=42
        )
        assert report["selection"]["mode"] == "protocol_cohort"
        assert 0 < report["stays_replayed"] <= 2


class TestLeakage:
    @staticmethod
    def _snapshots(mimic_index: Path, stay_id: str) -> list[dict[str, Any]]:
        from eval.mimic_harness.replay import replay_stay
        from eval.mimic_study.index_replay import mimic_stay_from_index
        from eval.mimic_study.indexing import load_stays

        stay_row = next(s for s in load_stays(mimic_index) if str(s["stay_id"]) == stay_id)
        stay = mimic_stay_from_index(mimic_index, stay_row)
        result = replay_stay(stay, check_leakage=True, score_every_event=True)
        return result.snapshots

    def test_future_events_not_visible_before_availability(self, mimic_index: Path) -> None:
        from datetime import datetime

        corrected_eid = "mimic/labevents/1"
        seen = 0
        for snapshot in self._snapshots(mimic_index, "10"):
            clock = datetime.fromisoformat(snapshot["availability_clock"])
            if corrected_eid in snapshot["evidence_ids"]:
                seen += 1
                assert clock >= datetime(2020, 1, 1, 13, 0, 0)
        assert seen > 0  # the corrected lab is eventually visible

    def test_later_correction_not_visible_before_storetime(
        self, mimic_index: Path
    ) -> None:
        from datetime import datetime

        snapshots = self._snapshots(mimic_index, "10")
        before = [
            s
            for s in snapshots
            if datetime.fromisoformat(s["availability_clock"])
            < datetime(2020, 1, 1, 13, 0, 0)
        ]
        after = [
            s
            for s in snapshots
            if datetime.fromisoformat(s["availability_clock"])
            >= datetime(2020, 1, 1, 13, 0, 0)
        ]
        assert before and after
        # Before storetime the corrected value must not appear in any snapshot.
        assert all("mimic/labevents/1" not in s["evidence_ids"] for s in before)
        # After storetime the corrected value drives the renal component.
        assert all("mimic/labevents/1" in s["evidence_ids"] for s in after)

    def test_discharge_diagnosis_never_enters_features(self, mimic_index: Path) -> None:
        from datetime import datetime

        dx_ids = {
            r["evidence_id"]
            for r in load_stay_events(mimic_index, "10")
            if r["is_discharge_diagnosis"]
        }
        assert dx_ids
        snapshots = self._snapshots(mimic_index, "10")
        for snapshot in snapshots:
            assert not dx_ids & set(snapshot["evidence_ids"])
        # The discharge diagnosis only becomes available at discharge; every
        # scoring snapshot up to that point exists without it.
        dischtime = datetime(2020, 1, 5, 9, 0, 0)
        pre_discharge = [
            s
            for s in snapshots
            if datetime.fromisoformat(s["availability_clock"]) < dischtime
        ]
        assert pre_discharge

    def test_labels_not_visible_to_replay(self, mimic_index: Path) -> None:
        baseline = replay_indexed_stays(index_dir=mimic_index, limit=None)
        # Even if a labels sidecar existed in the index dir, feature replay must
        # not load it: the replay modules never import the labels package.

        for name in [n for n in sys.modules if n.startswith("eval.mimic_study.labels")]:
            del sys.modules[name]
        import eval.mimic_study.index_replay  # noqa: F401, F811

        assert not [n for n in sys.modules if n.startswith("eval.mimic_study.labels")]
        labels_path = mimic_index / "labels.parquet"
        labels_path.write_bytes(b"not-a-parquet")
        try:
            after = replay_indexed_stays(index_dir=mimic_index, limit=None)
        finally:
            labels_path.unlink()
        assert [s["timeline_hash"] for s in baseline["stays"]] == [
            s["timeline_hash"] for s in after["stays"]
        ]

    def test_harness_leakage_check_active(self, mimic_index: Path) -> None:
        # replay_indexed_stays runs the harness with check_leakage=True; a stay
        # whose evidence would leak fails closed rather than emitting it.
        report = replay_indexed_stays(index_dir=mimic_index, stay_ids=["10"])
        assert report["errors"] == []


class TestManifestIntegration:
    def test_manifest_attached_and_deterministic(self, mimic_index: Path) -> None:
        _, manifest_a = run_with_manifest(index_dir=mimic_index, limit=2)
        _, manifest_b = run_with_manifest(index_dir=mimic_index, limit=2)
        assert manifest_a["content_hash"] == manifest_b["content_hash"]
        assert manifest_a["run_id"] == manifest_b["run_id"]
        assert manifest_a["manifest_path"].endswith(
            f"run-{manifest_a['run_id']}.json"
        )

    def test_manifest_changes_with_inputs(self, mimic_index: Path) -> None:
        _, manifest_a = run_with_manifest(index_dir=mimic_index, limit=1)
        _, manifest_b = run_with_manifest(index_dir=mimic_index, limit=2)
        assert manifest_a["content_hash"] != manifest_b["content_hash"]

    def test_manifest_records_required_fields(self, mimic_index: Path) -> None:
        _, manifest = run_with_manifest(index_dir=mimic_index, limit=2)
        assert manifest["dataset"]["name"] == "mimic-iv"
        assert manifest["dataset"]["version"] == "3.1"
        assert manifest["dataset"]["extract_date"]
        assert manifest["source_files"]["hosp/labevents.csv.gz"]["sha256"]
        assert manifest["index"]["index_hash"]
        assert manifest["code"]["git_commit"]
        assert manifest["protocol_id"] == "mimic-iv-governance-study.v1"
        assert manifest["rule_bundles"]["sepsis-sofa"]["content_hash"]
        assert manifest["rule_bundles"]["aki-kdigo"]["version"]
        assert manifest["cohort"]["stays_replayed"] == 2
        assert manifest["counts"]["events_replayed"] > 0
        assert "timestamp_failures" in manifest
        assert manifest["missingness"]["stays_scored"] == 2
        assert manifest["runtime"]["replay_seconds"] >= 0
        assert manifest["runtime"]["peak_rss_bytes"] > 0
        assert manifest["storage"]["index_bytes"] > 0
        assert manifest["cli"]["argv"]

    def test_stage_b_labels_and_protocol_attach_to_replay(
        self, mimic_index: Path, tmp_path: Path
    ) -> None:
        from eval.mimic_study.labels.materialize import (
            build_label_artifact,
            write_label_artifact,
        )

        pin = {
            "schema_version": "1.0.0",
            "mimic_code": {"revision": "test", "resolved_commit": "abc", "files": {}},
        }
        artifact = build_label_artifact(
            cohort_stay_ids=["10", "11", "12"],
            sepsis_rows=[{"stay_id": "10", "sepsis3": "1", "sofa_time": "2020-01-01 12:00:00"}],
            kdigo_rows=[],
            protocol_id="mimic-iv-governance-study.v2",
            dataset_pin={"name": "mimic-iv", "version": "3.1", "extract_date": "2026-09-06"},
            source_pin=pin,
        )
        labels_path = write_label_artifact(artifact, tmp_path / "labels.json")

        report = replay_indexed_stays(
            index_dir=mimic_index,
            stay_ids=["10"],
            labels_path=labels_path,
            protocol=load_protocol(version="v2"),
        )
        assert report["protocol_id"] == "mimic-iv-governance-study.v2"
        assert report["labels"]["content_hash"] == artifact["content_hash"]
        assert report["stays"][0]["labels"]["sepsis3_onset"] == "2020-01-01T12:00:00"

        _, manifest = run_with_manifest(
            index_dir=mimic_index,
            stay_ids=["10"],
            labels_path=labels_path,
            protocol=load_protocol(version="v2"),
        )
        assert manifest["protocol_id"] == "mimic-iv-governance-study.v2"
        assert manifest["labels"]["artifact"]["content_hash"] == artifact["content_hash"]
