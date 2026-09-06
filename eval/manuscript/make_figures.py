"""Render JAMIA Open manuscript figures 3 and 4 from committed frozen sidecars.

Offline figure generation (CI commits only the JSON specs, per the manuscript
package design). Reads:

  - eval/challenge2019/frozen/comparators_setB_window_m12_p6.v1.json
  - eval/challenge2019/frozen/ablation_setB_window_m12_p6.v1.json
  - eval/challenge2019/frozen/holdout_primary_window_m12_p6.v2.json
  - eval/manuscript/generated/figure_specs.v2.json

Writes PNG (300 dpi) + PDF to eval/manuscript/generated/figures/.

    python -m eval.manuscript.make_figures
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager  # noqa: F401  (kept for local font discovery)

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "eval" / "challenge2019" / "frozen"
GEN = ROOT / "eval" / "manuscript" / "generated"
OUT = GEN / "figures"
PAPER_FIG = ROOT / "paper" / "figures"

# Okabe-Ito colorblind-safe palette
BLUE = "#0072B2"
VERMILLION = "#D55E00"
GREY = "#6E6E6E"
INK = "#1b1b1b"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.edgecolor": "#444444",
        "axes.linewidth": 0.8,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": "#444444",
        "ytick.color": "#444444",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 300,
    }
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _save(fig, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{stem}.{ext}", bbox_inches="tight", facecolor="white")
        fig.savefig(PAPER_FIG / f"{stem}.{ext}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figure3_detection_burden() -> None:
    """SetB detection/burden plane: sensitivity vs in-window emissions (log x)."""
    comp = _load(FROZEN / "comparators_setB_window_m12_p6.v1.json")
    abl = _load(FROZEN / "ablation_setB_window_m12_p6.v1.json")
    primary = next(v for v in abl["variants"] if v["id"] == "primary_operating_point")

    sepsis_stays = comp["comparators"][0]["cohort"]["sepsis_stays"]  # 1142
    gov_tp = primary["governed_sensitivity"] * sepsis_stays

    # Curie lanes (from committed ablation sidecar); NNA = emissions / in-window TP
    curie = [
        {
            "label": "Threshold-only SOFA",
            "sens": primary["naive_sensitivity"],
            "emis": primary["naive_total"],
            "nna": primary["naive_total"] / gov_tp,
            "color": INK,
            "marker": "D",
            "kind": "naive",
        },
        {
            "label": "Governed SOFA (watch + page)",
            "sens": primary["governed_sensitivity"],
            "emis": primary["governed_total"],
            "nna": primary["governed_total"] / gov_tp,
            "color": BLUE,
            "marker": "o",
            "kind": "curie",
        },
        {
            "label": "Interruptive lane",
            "sens": primary["interruptive_sensitivity"],
            "emis": primary["interruptive_total"],
            "nna": primary["interruptive_nna"],
            "color": VERMILLION,
            "marker": "o",
            "kind": "curie",
        },
    ]
    comps = [
        {
            "label": c["title"].split(" (")[0],
            "sens": c["metrics"]["sensitivity"],
            "emis": c["metrics"]["emissions"],
            "nna": c["metrics"]["nna"],
        }
        for c in comp["comparators"]
    ]

    fig, ax = plt.subplots(figsize=(6.6, 4.6))

    # "better" direction guide (up + left)
    ax.annotate(
        "better",
        xy=(0.06, 0.94),
        xytext=(0.22, 0.82),
        xycoords="axes fraction",
        textcoords="axes fraction",
        fontsize=8.5,
        color=GREY,
        ha="center",
        arrowprops=dict(arrowstyle="->", color=GREY, lw=1.0),
    )

    # comparators (ungoverned reference family)
    for c in comps:
        ax.scatter(
            c["emis"], c["sens"] * 100, s=64, marker="s",
            facecolor="white", edgecolor=GREY, linewidth=1.4, zorder=3,
        )
    # Curie lanes
    for p in curie:
        ax.scatter(
            p["emis"], p["sens"] * 100, s=118 if p["kind"] == "curie" else 90,
            marker=p["marker"],
            facecolor=p["color"] if p["kind"] == "curie" else "white",
            edgecolor=p["color"], linewidth=1.8, zorder=5,
        )

    # labels
    def _lab(x, y, text, dx, dy, color, ha="left"):
        ax.annotate(
            text, xy=(x, y), xytext=(x * dx, y + dy), fontsize=8.6,
            color=color, ha=ha, va="center", zorder=6,
        )

    _lab(comps[0]["emis"], comps[0]["sens"] * 100, "SIRS ≥ 2\nNNA 213", 1.06, 2.4, GREY)
    _lab(comps[1]["emis"], comps[1]["sens"] * 100, "NEWS2 ≥ 5*\nNNA 163", 1.06, -3.0, GREY)
    _lab(comps[2]["emis"], comps[2]["sens"] * 100, "qSOFA ≥ 2*\nNNA 78", 1.07, 0, GREY)
    _lab(
        curie[0]["emis"], curie[0]["sens"] * 100,
        f"Threshold-only SOFA\nNNA {curie[0]['nna']:.0f}", 1.05, 3.0, INK,
    )
    _lab(
        curie[1]["emis"], curie[1]["sens"] * 100,
        f"Governed SOFA\n(watch + page) · NNA {curie[1]['nna']:.0f}",
        0.60, 3.4, BLUE, ha="right",
    )
    _lab(
        curie[2]["emis"], curie[2]["sens"] * 100,
        f"Interruptive lane\nNNA {curie[2]['nna']:.0f}", 1.07, 0, VERMILLION,
    )

    ax.set_xscale("log")
    ax.set_xlim(1.6e4, 5.2e5)
    ax.set_ylim(18, 90)
    from matplotlib.ticker import FixedLocator, NullLocator

    ticks = [2e4, 3e4, 5e4, 1e5, 2e5, 5e5]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels(["20k", "30k", "50k", "100k", "200k", "500k"])
    ax.set_xlabel("In-window emissions on setB  (log scale — lower is quieter)")
    ax.set_ylabel("In-window sensitivity  (%)")
    ax.grid(True, which="both", axis="both", color="#e8e8e8", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # legend proxies
    from matplotlib.lines import Line2D

    handles = [
        Line2D(
            [0], [0], marker="o", color="w", markerfacecolor=BLUE,
            markeredgecolor=BLUE, markersize=9, label="Governed Curie lane",
        ),
        Line2D(
            [0], [0], marker="o", color="w", markerfacecolor=VERMILLION,
            markeredgecolor=VERMILLION, markersize=9, label="Interruptive lane",
        ),
        Line2D(
            [0], [0], marker="D", color="w", markerfacecolor="white",
            markeredgecolor=INK, markersize=8, label="Threshold-only SOFA",
        ),
        Line2D(
            [0], [0], marker="s", color="w", markerfacecolor="white",
            markeredgecolor=GREY, markersize=8,
            label="Bedside comparator (ungoverned)",
        ),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8.2, handletextpad=0.4)

    ax.set_title(
        "SetB detection vs interruption burden  (window_m12_p6)",
        fontsize=11, fontweight="bold", loc="left", pad=10,
    )
    fig.text(
        0.012, -0.02,
        "*NEWS2 omits consciousness/AVPU; qSOFA omits GCS (absent in Challenge 2019). "
        "NNA = emissions per in-window true-positive stay. "
        "Not a claim of clinical superiority.",
        fontsize=7.0, color=GREY,
    )
    _save(fig, "figure3_detection_burden")


def figure4_timing_robustness() -> None:
    """Naive vs governed sensitivity across secondary timing definitions."""
    specs = _load(GEN / "figure_specs.v2.json")
    holdout = _load(FROZEN / "holdout_primary_window_m12_p6.v2.json")
    primary = holdout["detection"]["governed_sensitivity"] * 100

    rows = sorted(specs["robustness"]["rows"], key=lambda r: r["governed_sensitivity"])
    labels = {
        "early_only": "early-only",
        "grace_0": "grace-0 h",
        "grace_6": "grace-6 h",
        "grace_12": "grace-12 h",
        "window_pm12": "±12 h",
    }
    names = [labels[r["detection_mode_id"]] for r in rows]
    naive = [r["naive_sensitivity"] * 100 for r in rows]
    gov = [r["governed_sensitivity"] * 100 for r in rows]

    import numpy as np

    x = np.arange(len(rows))
    w = 0.38

    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    ax.bar(
        x - w / 2, naive, w, label="Naive (threshold-only)", color="#c9d6df",
        edgecolor="#8a99a4", linewidth=0.7,
    )
    ax.bar(x + w / 2, gov, w, label="Governed", color=BLUE, edgecolor="#005a8f", linewidth=0.7)

    for xi, (n, g) in enumerate(zip(naive, gov)):
        ax.text(xi + w / 2, g + 1.2, f"{g:.1f}", ha="center", va="bottom", fontsize=7.8, color=BLUE)

    ax.axhline(primary, color=VERMILLION, linestyle="--", linewidth=1.3, zorder=5)
    ax.text(
        -0.4, primary + 1.2,
        f"Primary window_m12_p6 = {primary:.1f}%",
        ha="left", va="bottom", fontsize=8.2, color=VERMILLION, fontweight="bold",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 100)
    ax.set_ylabel("In-window sensitivity  (%)")
    ax.grid(True, axis="y", color="#ececec", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, fontsize=8.4)
    ax.set_title(
        "Governance retains naive detection across timing definitions  (setB)",
        fontsize=11, fontweight="bold", loc="left", pad=10,
    )
    fig.text(
        0.012, -0.03,
        "Secondary sensitivity analyses; naive and governed sensitivity are equal "
        "for the frozen winner in every definition. "
        "The 81.1% grace-6 h value is secondary, not the primary result.",
        fontsize=7.0, color=GREY,
    )
    _save(fig, "figure4_timing_robustness")


def main() -> None:
    figure3_detection_burden()
    figure4_timing_robustness()
    print(f"Wrote figures to {OUT.relative_to(ROOT)}/")
    for f in sorted(OUT.glob("*")):
        print("  ", f.relative_to(ROOT), f.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
