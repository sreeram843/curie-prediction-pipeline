"""Render the JBHI graphical abstract (IEEE: 660 x 295 px, >=16 px sans-serif labels).

Every number is read from the frozen MIMIC-IV sidecars, like the manuscript figures.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "eval" / "mimic_study" / "frozen"
OUT = Path(__file__).resolve().parent / "figures" / "graphical_abstract.png"

W, H, DPI = 660, 295, 100  # pixels; DPI 100 so 1 pt = 100/72 px
PX = 72 / DPI  # points per pixel

NAVY, GREY, RED, INK = "#1f4e79", "#e8edf3", "#b00020", "#1a1a1a"


def _numbers() -> dict[str, str]:
    manifest = json.loads((FROZEN / "study_manifest.v3.json").read_text())["test_primary"]
    agg = json.loads((FROZEN / "publication_aggregates.v1.json").read_text())
    lead = agg["test_timing_and_labels"]["lead_gated_min_2h"]["governed_sensitivity"]["point"]
    return {
        "stays": f"{manifest['stays']:,}",
        "sens": f"{100 * manifest['governed_sensitivity']:.1f}%",
        "ratio": f"{100 * manifest['interruptive_reduction_ratio']:.1f}%",
        "lead": f"{100 * lead:.1f}%",
        "prec": f"{100 * manifest['interruptive_precision']:.1f}%",
    }


def _box(ax, x, y, w, h, title, body) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=8",
            fc=GREY, ec=NAVY, lw=1.5,
        )
    )
    ax.text(x + w / 2, y + h - 12, title, ha="center", va="top", color=NAVY,
            fontsize=17 * PX, fontweight="bold")
    ax.text(x + w / 2, y + 16, body, ha="center", va="bottom", color=INK,
            fontsize=16 * PX, linespacing=1.15)


def _arrow(ax, x0, x1, y) -> None:
    ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle="-|>", mutation_scale=14,
                                 color=NAVY, lw=1.6))


def main() -> int:
    n = _numbers()
    plt.rcParams.update({"font.family": ["Arial", "Helvetica", "DejaVu Sans"]})
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    top, bh, bw = 160, 122, 190
    xs = (14, 235, 456)
    _box(ax, xs[0], top, bw, bh, "ICU EHR data", "MIMIC-IV\neICU-CRD")
    _box(ax, xs[1], top, bw, bh, "SOFA score", "missing input\n→ flagged, not 0")
    _box(ax, xs[2], top, bw, bh, "Governance", "passive record\nvs interruption")
    for a, b in ((xs[0] + bw, xs[1]), (xs[1] + bw, xs[2])):
        _arrow(ax, a + 4, b - 4, top + bh / 2)

    ax.text(W / 2, 140, f"Locked MIMIC-IV test set, {n['stays']} ICU stays",
            ha="center", va="center", color=INK, fontsize=16 * PX, fontweight="bold")
    stats = (
        (n["sens"], "governed detection", NAVY),
        (n["ratio"], "of naive pages", NAVY),
        (n["lead"], "detected ≥ 2 h early", RED),
        (n["prec"], "page precision", RED),
    )
    cw = W / len(stats)
    for i, (value, label, color) in enumerate(stats):
        cx = cw * (i + 0.5)
        ax.text(cx, 88, value, ha="center", va="center", color=color,
                fontsize=26 * PX, fontweight="bold")
        ax.text(cx, 50, label, ha="center", va="center", color=INK, fontsize=16 * PX)
    ax.text(W / 2, 14, "Retrospective research prototype; not clinical validation",
            ha="center", va="center", color="#555555", fontsize=16 * PX, style="italic")

    OUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUT, dpi=DPI, facecolor="white")
    plt.close(fig)
    # Same pixels; IEEE asks for >=300 dpi metadata.
    Image.open(OUT).convert("RGB").save(OUT, dpi=(300, 300), optimize=True)
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
