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
    assert "Challenge utility" in holdout
    assert "alerts / patient-day" in holdout
    assert "stay-level PPV" in holdout
    comparators = (out / "comparators_tabular.tex").read_text(encoding="utf-8")
    assert "191294" in comparators
    assert "311797" in comparators
    miss = (out / "miss_tabular.tex").read_text(encoding="utf-8")
    assert miss.index("141") < miss.index("58") < miss.index("35")
    ablation = (out / "ablation_tabular.tex").read_text(encoding="utf-8")
    assert "All emits interruptive" not in ablation
    assert "Page gate disabled" in ablation
    selection = (out / "selection_grid_tabular.tex").read_text(encoding="utf-8")
    assert selection.count(" & ") == 8 * 24
    assert selection.count("yes") == 1
    assert "grid\\_p0\\_r90\\_b0" in selection
    assert not (tmp_path / "holdout_tabular.tex").read_text(encoding="utf-8").isspace()
