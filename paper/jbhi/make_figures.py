"""Render JBHI figures from the frozen publication aggregates only."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SIDECAR = ROOT / "eval" / "mimic_study" / "frozen" / "publication_aggregates.v1.json"
OUT_DIR = Path(__file__).resolve().parent / "figures"


def lead_time_figure(body: dict) -> Path:
    timing = body["test_timing_and_labels"]
    lead = timing["lead_time_governed"]
    bins = lead["histogram_hours"]
    labeled = timing["labeled_positive"]
    centers = [(b["lo"] + b["hi"]) / 2 for b in bins]
    counts = [b["count"] or 0 for b in bins]
    colors = ["#b0b0b0" if b["hi"] <= 2 else "#1f4e79" for b in bins]

    # STIX ships with matplotlib (Times-like, matches IEEEtran); TrueType embedding avoids the
    # Type 3 fonts that IEEE PDF eXpress rejects.
    plt.rcParams.update(
        {
            "font.family": "STIXGeneral",
            "mathtext.fontset": "stix",
            "font.size": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig, ax = plt.subplots(figsize=(3.45, 2.1))
    ax.bar(centers, counts, width=1.8, color=colors, edgecolor="black", linewidth=0.4)
    ax.axvline(2, color="#c00000", linestyle="--", linewidth=0.9)
    share = lead["lead_ge_2h"] / labeled
    ax.text(
        2.3,
        max(counts) * 0.93,
        f"lead $\\geq$ 2 h: {lead['lead_ge_2h']:,}/{labeled:,} ({100 * share:.1f}%)",
        color="#c00000",
        fontsize=7,
        va="top",
    )
    ax.set_xlabel("Hours before onset (negative = after onset)")
    ax.set_ylabel("Labeled-positive stays")
    ax.set_xticks(range(-6, 13, 2))
    ax.set_xlim(-6.5, 12.5)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(pad=0.3)
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "lead_time_distribution.pdf"
    fig.savefig(out)
    fig.savefig(out.with_suffix(".png"), dpi=300)
    plt.close(fig)
    return out


def main() -> int:
    body = json.loads(SIDECAR.read_text())
    print(lead_time_figure(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
