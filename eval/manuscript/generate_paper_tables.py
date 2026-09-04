"""Emit ``paper/tables/*`` from frozen Challenge 2019 sidecars.

Do not hand-edit the generated ``*_tabular.tex`` or CSV files. Regenerate with:

    python -m eval.manuscript.generate_paper_tables
"""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "eval" / "challenge2019" / "frozen"
DEFAULT_TABLES = ROOT / "paper" / "tables"
FIGURE_SRC = ROOT / "eval" / "manuscript" / "generated" / "figures"
FIGURE_DST = ROOT / "paper" / "figures"

ABLATION_NOTES = {
    "primary_operating_point": "Frozen winner",
    "drop_baseline": "Null (already off)",
    "drop_persistence": "No change on hourly rows",
    "drop_crossings": "No change on hourly rows",
    "drop_refractory": "Watch volume = naive",
    "drop_page_gate": "All emits interruptive",
}

MISS_LABELS = {
    "scorer_threshold": "Never crossed naive SOFA threshold in-window",
    "timing_window": "Governed emit only outside the window",
    "missing_input": "Never scoreable (missing inputs)",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((FROZEN / name).read_text(encoding="utf-8"))


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "---"
    return f"{100.0 * value:.{digits}f}"


def _ci_pct(block: dict[str, Any] | None) -> str:
    if not block:
        return "---"
    return f"{100.0 * block['low']:.1f}--{100.0 * block['high']:.1f}"


def _ci_num(block: dict[str, Any] | None, digits: int = 1) -> str:
    if not block:
        return "---"
    return f"{block['low']:.{digits}f}--{block['high']:.{digits}f}"


def _tex_text(value: str) -> str:
    return (
        value.replace("\\", r"\textbackslash{}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("_", r"\_")
        .replace("≥", r"$\geq$")
        .replace("≤", r"$\leq$")
        .replace("→", r"$\rightarrow$")
    )


def _tabular(align: str, header: str, rows: list[str]) -> str:
    body = "\n".join(rows)
    return (
        f"\\begin{{tabular}}{{{align}}}\n"
        "\\toprule\n"
        f"{header} \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
    )


def _write_tex(tables_dir: Path, name: str, body: str) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    (tables_dir / name).write_text(body.rstrip() + "\n", encoding="utf-8")


def _write_csv(tables_dir: Path, name: str, header: list[str], rows: list[list[Any]]) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    with (tables_dir / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def holdout_rows() -> tuple[str, list[list[Any]]]:
    v1 = _load("holdout_primary_window_m12_p6.v1.json")
    v2 = _load("holdout_primary_window_m12_p6.v2.json")
    det = v1["detection"]
    boot = v2.get("bootstrap") or {}
    ablation = _load("ablation_setB_window_m12_p6.v1.json")
    primary = next(v for v in ablation["variants"] if v["id"] == "primary_operating_point")
    lines = [
        (
            r"Governed sensitivity (\%)",
            f"{100 * det['governed_sensitivity']:.1f}",
            _ci_pct(boot.get("governed_sensitivity")),
            "Any governed emission in-window",
        ),
        (
            r"Interruptive sensitivity (\%)",
            f"{100 * det['interruptive_sensitivity']:.1f}",
            _ci_pct(boot.get("interruptive_sensitivity")),
            "Interruptive emission in-window",
        ),
        (
            "Interruptive NNA",
            f"{det['interruptive_nna']:.1f}",
            _ci_num(boot.get("interruptive_nna")),
            "Interruptive emissions / interruptive TP stay",
        ),
        (
            "Interruptive / naive emissions",
            f"{primary['interruptive_reduction_ratio']:.3f}",
            _ci_num(boot.get("interruptive_reduction_ratio"), 3),
            "Page-eligible vs threshold-only SOFA",
        ),
        (
            "Mean in-window lead (h)",
            f"{det['mean_lead_hours_in_window']:.2f}",
            _ci_num(boot.get("mean_lead_hours_governed_in_window"), 2),
            r"First governed emission to \texttt{label\_start}",
        ),
    ]
    tex_rows = [f"{a} & {b} & {c} & {d} \\\\" for a, b, c, d in lines]
    tex = _tabular(
        "@{}lccc@{}",
        r"Metric & Result & 95\% CI & Interpretation",
        tex_rows,
    )
    csv_rows = [
        [a.replace(r"(\%)", "(%)").replace(r"\texttt{label\_start}", "label_start"), b, c, d]
        for a, b, c, d in lines
    ]
    return tex, csv_rows


def comparator_rows() -> tuple[str, list[list[Any]]]:
    comps = _load("comparators_setB_window_m12_p6.v1.json")["comparators"]
    ablation = _load("ablation_setB_window_m12_p6.v1.json")
    primary = next(v for v in ablation["variants"] if v["id"] == "primary_operating_point")
    sepsis = comps[0]["cohort"]["sepsis_stays"]
    naive_tp = primary["naive_sensitivity"] * sepsis
    gov_tp = primary["governed_sensitivity"] * sepsis
    extra = [
        {
            "title": "Threshold-only partial SOFA",
            "metrics": {
                "sensitivity": primary["naive_sensitivity"],
                "emissions": primary["naive_total"],
                "nna": primary["naive_total"] / naive_tp if naive_tp else None,
            },
        },
        {
            "title": "Governed partial SOFA (any emit)",
            "metrics": {
                "sensitivity": primary["governed_sensitivity"],
                "emissions": primary["governed_total"],
                "nna": primary["governed_total"] / gov_tp if gov_tp else None,
            },
        },
        {
            "title": "Interruptive governed lane",
            "metrics": {
                "sensitivity": primary["interruptive_sensitivity"],
                "emissions": primary["interruptive_total"],
                "nna": primary["interruptive_nna"],
            },
        },
    ]
    tex_rows = []
    csv_rows = []
    for card in list(comps) + extra:
        metrics = card["metrics"]
        title = str(card.get("title") or card.get("id"))
        nna = metrics.get("nna")
        nna_s = "---" if nna is None else f"{nna:.1f}"
        tex_rows.append(
            f"{_tex_text(title)} & {_pct(metrics.get('sensitivity'))} & "
            f"{int(metrics['emissions'])} & {nna_s} \\\\"
        )
        csv_rows.append([title, metrics.get("sensitivity"), metrics.get("emissions"), nna])
    tex = _tabular(
        "@{}lccc@{}",
        r"Policy & Sensitivity (\%) & Emissions & NNA",
        tex_rows,
    )
    return tex, csv_rows


def ablation_rows() -> tuple[str, list[list[Any]]]:
    tex_rows = []
    csv_rows = []
    for row in _load("ablation_setB_window_m12_p6.v1.json")["variants"]:
        note = ABLATION_NOTES.get(row["id"], "")
        tex_rows.append(
            f"{_tex_text(row['id'])} & {_pct(row['governed_sensitivity'])} & "
            f"{_pct(row['interruptive_sensitivity'])} & "
            f"{row['interruptive_reduction_ratio']:.3f} & "
            f"{row['interruptive_nna']:.1f} & {_tex_text(note)} \\\\"
        )
        csv_rows.append(
            [
                row["id"],
                row["governed_sensitivity"],
                row["interruptive_sensitivity"],
                row["interruptive_reduction_ratio"],
                row["interruptive_nna"],
                note,
            ]
        )
    tex = _tabular(
        "@{}lccccp{3.4cm}@{}",
        r"Variant & Gov.\ sens.\ (\%) & Int.\ sens.\ (\%) & Int.\ reduction & Int.\ NNA & Note",
        tex_rows,
    )
    return tex, csv_rows


def miss_rows() -> tuple[str, list[list[Any]]]:
    reasons = list(_load("miss_analysis.v2.json")["by_primary_reason"])
    reasons.sort(key=lambda row: (-int(row["count"]), str(row["reason"])))
    tex_rows = []
    csv_rows = []
    for row in reasons:
        label = MISS_LABELS.get(row["reason"], row["reason"])
        tex_rows.append(f"{_tex_text(label)} & {row['count']} & {100 * row['rate']:.1f} \\\\")
        csv_rows.append([row["reason"], row["count"], row["rate"]])
    tex = _tabular(
        "@{}lcc@{}",
        r"Reason & Count & Rate (\%)",
        tex_rows,
    )
    return tex, csv_rows


def robustness_rows() -> tuple[str, list[list[Any]]]:
    tex_rows = []
    csv_rows = []
    for row in _load("robustness_summary.v1.json")["modes"]:
        tex_rows.append(
            f"{_tex_text(row['definition'])} & {_pct(row['naive_sensitivity'])} & "
            f"{_pct(row['governed_sensitivity'])} \\\\"
        )
        csv_rows.append(
            [
                row["detection_mode_id"],
                row["definition"],
                row["naive_sensitivity"],
                row["governed_sensitivity"],
            ]
        )
    tex = _tabular(
        "@{}lcc@{}",
        r"Definition & Naive sensitivity (\%) & Governed sensitivity (\%)",
        tex_rows,
    )
    return tex, csv_rows


def pareto_rows() -> tuple[str, list[list[Any]]]:
    tex_rows = []
    csv_rows = []
    for row in _load("pareto_named_profiles.v1.json")["points"]:
        mark = "yes" if row.get("selected") else "no"
        tex_rows.append(
            f"{_tex_text(str(row['candidate_id']))} & {_pct(row['governed_sensitivity'])} & "
            f"{row['interruptive_reduction_ratio']:.3f} & "
            f"{_pct(row['interruptive_sensitivity'])} & {mark} \\\\"
        )
        csv_rows.append(
            [
                row["candidate_id"],
                row["governed_sensitivity"],
                row["interruptive_reduction_ratio"],
                row["interruptive_sensitivity"],
                row.get("selected"),
            ]
        )
    tex = _tabular(
        "@{}lcccc@{}",
        r"Candidate & Gov.\ sens.\ (\%) & Int.\ reduction & Int.\ sens.\ (\%) & Selected",
        tex_rows,
    )
    return tex, csv_rows


def _copy_figures() -> None:
    if not FIGURE_SRC.is_dir():
        return
    FIGURE_DST.mkdir(parents=True, exist_ok=True)
    for path in FIGURE_SRC.glob("figure*"):
        shutil.copy2(path, FIGURE_DST / path.name)


def write_all(*, tables_dir: Path | None = None) -> Path:
    dest = tables_dir or DEFAULT_TABLES
    mapping: list[tuple[str, str, Callable[[], tuple[str, list[list[Any]]]], list[str]]] = [
        ("holdout_tabular.tex", "holdout.csv", holdout_rows, ["metric", "point", "ci95", "note"]),
        (
            "comparators_tabular.tex",
            "comparators.csv",
            comparator_rows,
            ["policy", "sensitivity", "emissions", "nna"],
        ),
        (
            "ablation_tabular.tex",
            "ablation.csv",
            ablation_rows,
            ["variant", "gov_sens", "int_sens", "int_reduction", "int_nna", "note"],
        ),
        ("miss_tabular.tex", "miss.csv", miss_rows, ["reason", "count", "rate"]),
        (
            "robustness_tabular.tex",
            "robustness.csv",
            robustness_rows,
            ["mode_id", "definition", "naive_sensitivity", "governed_sensitivity"],
        ),
        (
            "pareto_tabular.tex",
            "pareto.csv",
            pareto_rows,
            [
                "candidate_id",
                "governed_sensitivity",
                "interruptive_reduction_ratio",
                "interruptive_sensitivity",
                "selected",
            ],
        ),
    ]
    for tex_name, csv_name, fn, header in mapping:
        tex, rows = fn()
        _write_tex(dest, tex_name, tex)
        _write_csv(dest, csv_name, header, rows)
    if tables_dir is None:
        _copy_figures()
    return dest


def main() -> int:
    out = write_all()
    print(f"Wrote tables under {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
