#!/usr/bin/env bash
# Assemble paper/jamiaopen/submission/ from current built PDFs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JO="$ROOT/jamiaopen"
SUB="$JO/submission"

need() {
  if [[ ! -f "$1" ]]; then
    echo "missing required file: $1" >&2
    exit 1
  fi
}

need "$ROOT/main.pdf"
need "$JO/cover_letter.pdf"
need "$JO/supplement.pdf"
need "$JO/figure1-system-boundary.pdf"
need "$ROOT/figures/figure3_detection_burden.pdf"
need "$ROOT/figures/figure4_timing_robustness.pdf"

mkdir -p "$SUB/figures" "$SUB/portal_metadata"

cp "$JO/cover_letter.pdf" "$SUB/01_cover_letter.pdf"
cp "$ROOT/main.pdf" "$SUB/02_manuscript_main.pdf"
cp "$JO/supplement.pdf" "$SUB/03_supplementary_material.pdf"

cp "$JO/figure1-system-boundary.pdf" "$SUB/figures/Figure1_system_boundary.pdf"
cp "$ROOT/figures/figure3_detection_burden.pdf" "$SUB/figures/Figure2_detection_burden.pdf"
cp "$ROOT/figures/figure4_timing_robustness.pdf" "$SUB/figures/Figure3_timing_robustness.pdf"

cp "$ROOT/figures/figure3_detection_burden.png" "$SUB/figures/Figure2_detection_burden.png"
cp "$ROOT/figures/figure4_timing_robustness.png" "$SUB/figures/Figure3_timing_robustness.png"

if command -v pdftoppm >/dev/null 2>&1; then
  pdftoppm -png -r 300 "$JO/figure1-system-boundary.pdf" "$SUB/figures/Figure1_system_boundary"
  if [[ -f "$SUB/figures/Figure1_system_boundary-1.png" ]]; then
    mv "$SUB/figures/Figure1_system_boundary-1.png" "$SUB/figures/Figure1_system_boundary.png"
  fi
fi

echo "Assembled $SUB"
find "$SUB" -type f | sort
