"""Generated paper tables must come from frozen sidecars, not hand-copied numbers."""

from __future__ import annotations

from pathlib import Path

from eval.manuscript.generate_paper_tables import write_all


def test_write_all_matches_frozen_holdout(tmp_path: Path) -> None:
    out = write_all(tables_dir=tmp_path)
    holdout = (out / "holdout_tabular.tex").read_text(encoding="utf-8")
    assert "79.5" in holdout
    assert "34.0" in holdout
    assert "106.1" in holdout
    assert "0.132" in holdout
    assert "5.97" in holdout
    assert "77.0--81.8" in holdout
    comparators = (out / "comparators_tabular.tex").read_text(encoding="utf-8")
    assert "191294" in comparators
    assert "311797" in comparators
    miss = (out / "miss_tabular.tex").read_text(encoding="utf-8")
    assert miss.index("141") < miss.index("58") < miss.index("35")
    assert not (tmp_path / "holdout_tabular.tex").read_text(encoding="utf-8").isspace()
