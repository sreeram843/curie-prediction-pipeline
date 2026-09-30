#!/usr/bin/env bash
# Assemble paper/ijmi/submission/ for Elsevier Editorial Manager (IJMI).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IJMI="$ROOT/ijmi"
JO="$ROOT/jamiaopen"
SUB="$IJMI/submission"

need() {
  if [[ ! -f "$1" ]]; then
    echo "missing required file: $1" >&2
    exit 1
  fi
}

need "$ROOT/main.pdf"
need "$IJMI/cover_letter.pdf"
need "$JO/supplement.pdf"
need "$JO/figure1-system-boundary.pdf"
need "$ROOT/figures/figure3_detection_burden.pdf"
need "$ROOT/figures/figure4_timing_robustness.pdf"
need "$IJMI/highlights.txt"
need "$IJMI/summary_table.txt"
need "$IJMI/competing_interests.pdf"

mkdir -p "$SUB/figures" "$SUB/portal_metadata"

cp "$IJMI/cover_letter.pdf" "$SUB/01_cover_letter.pdf"
cp "$ROOT/main.pdf" "$SUB/02_manuscript_main.pdf"
cp "$JO/supplement.pdf" "$SUB/03_supplementary_material.pdf"
cp "$IJMI/highlights.txt" "$SUB/04_highlights.txt"
cp "$IJMI/summary_table.txt" "$SUB/05_summary_table.txt"
cp "$IJMI/clinical_translation_roadmap.txt" "$SUB/06_clinical_translation_roadmap.txt"
cp "$IJMI/ml_checklist_note.txt" "$SUB/07_ml_checklist_note.txt"
cp "$IJMI/competing_interests.pdf" "$SUB/08_declaration_competing_interests.pdf"
cp "$IJMI/competing_interests.pdf" "$SUB/08_declaration_competing_interests.pdf"

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

# Portal paste helpers
cp "$JO/submission/portal_metadata/title.txt" "$SUB/portal_metadata/title.txt"
cp "$JO/submission/portal_metadata/keywords.txt" "$SUB/portal_metadata/keywords.txt"
cp "$JO/submission/portal_metadata/abstract.txt" "$SUB/portal_metadata/abstract.txt"
cp "$JO/submission/portal_metadata/data_code_availability.txt" "$SUB/portal_metadata/data_code_availability.txt"
printf '%s\n' 'Original research article' > "$SUB/portal_metadata/article_type.txt"
printf '%s\n' '1723' > "$SUB/portal_metadata/word_count.txt"

echo "Assembled $SUB"
find "$SUB" -type f | sort
