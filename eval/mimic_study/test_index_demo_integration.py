"""Integration tests: bounded index builds on the local PhysioNet demo data.

Requires ``data/mimic-iv-demo`` / ``data/eicu-crd-demo`` (PhysioNet open demo,
not committed). Skipped when absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyarrow")

from eval.mimic_study.index_replay import (  # noqa: E402
    benchmark,
    replay_indexed_stays,
    run_with_manifest,
)
from eval.mimic_study.indexing import (  # noqa: E402
    build_index,
    reconcile_source_to_index,
    validate_index,
)

pytestmark = pytest.mark.integration


def _require_dir(path: Path) -> Path:
    if not path.is_dir():
        pytest.skip(f"demo data missing: {path}")
    return path


@pytest.fixture(scope="module")
def mimic_demo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    source = _require_dir(Path("data") / "mimic-iv-demo")
    index_dir = tmp_path_factory.mktemp("mimic-demo-idx") / "idx"
    build_index(source_root=source, index_dir=index_dir, dataset="mimic", limit=20)
    return source, index_dir


@pytest.fixture(scope="module")
def eicu_demo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    source = _require_dir(Path("data") / "eicu-crd-demo")
    index_dir = tmp_path_factory.mktemp("eicu-demo-idx") / "idx"
    build_index(source_root=source, index_dir=index_dir, dataset="eicu", limit=20)
    return source, index_dir


class TestMimicDemo:
    def test_build_validate_reconcile(self, mimic_demo: tuple[Path, Path]) -> None:
        source, index_dir = mimic_demo
        assert validate_index(index_dir)["ok"]
        report = reconcile_source_to_index(
            source_root=source, index_dir=index_dir, dataset="mimic", limit=10
        )
        assert report["ok"], report["mismatches"][:3]
        assert report["rows_compared"] > 0

    def test_bounded_replay_with_manifest(self, mimic_demo: tuple[Path, Path]) -> None:
        _, index_dir = mimic_demo
        report, manifest = run_with_manifest(index_dir=index_dir, limit=5)
        assert report["stays_replayed"] == 5
        assert report["missingness"]["stays_scored"] == 5
        assert manifest["content_hash"]
        assert manifest["cohort"]["stays_replayed"] == 5

    def test_single_stay_equals_bounded(self, mimic_demo: tuple[Path, Path]) -> None:
        _, index_dir = mimic_demo
        bounded = replay_indexed_stays(index_dir=index_dir, limit=3)
        sid = bounded["selection"]["stay_ids"][0]
        single = replay_indexed_stays(index_dir=index_dir, stay_ids=[sid])
        assert single["stays"][0] == bounded["stays"][0]


class TestEicuDemo:
    def test_build_validate_reconcile(self, eicu_demo: tuple[Path, Path]) -> None:
        source, index_dir = eicu_demo
        assert validate_index(index_dir)["ok"]
        report = reconcile_source_to_index(
            source_root=source, index_dir=index_dir, dataset="eicu", limit=10
        )
        assert report["ok"], report["mismatches"][:3]
        assert report["rows_compared"] > 0

    def test_bounded_replay(self, eicu_demo: tuple[Path, Path]) -> None:
        _, index_dir = eicu_demo
        report = replay_indexed_stays(index_dir=index_dir, limit=5)
        assert report["stays_replayed"] == 5
        assert report["errors"] == []

    def test_benchmark_source_vs_index(self, eicu_demo: tuple[Path, Path]) -> None:
        source, index_dir = eicu_demo
        result = benchmark(source_root=source, index_dir=index_dir, dataset="eicu", limit=5)
        assert result["runtime_s"]["indexed_load_and_replay"] >= 0
        assert result["equivalence"]["final_snapshots_score_equivalent"]
        assert result["storage"]["index_bytes"] > 0


class TestMimicDemoBenchmark:
    def test_benchmark_source_vs_index(self, mimic_demo: tuple[Path, Path]) -> None:
        source, index_dir = mimic_demo
        result = benchmark(source_root=source, index_dir=index_dir, dataset="mimic", limit=5)
        # Clinical content of the emitted timelines must match exactly; the
        # indexed path may shift availability (storetime) without changing it.
        assert result["equivalence"]["event_content_equivalent"]
        # Indexed load+replay must not rescan the full compressed sources.
        assert result["runtime_s"]["ratio"] >= 1.0


def test_full_run_command_path(tmp_path_factory: pytest.TempPathFactory) -> None:
    """LIMIT=0 resolves to every indexed stay through the same code path."""
    source = _require_dir(Path("data") / "mimic-iv-demo")
    index_dir = tmp_path_factory.mktemp("mimic-full-idx") / "idx"
    meta = build_index(source_root=source, index_dir=index_dir, dataset="mimic", limit=0)
    report = replay_indexed_stays(index_dir=index_dir, limit=0)
    assert report["stays_replayed"] == meta["stays"]["total"]
    assert report["selection"]["mode"] == "full"
