#!/usr/bin/env bash
# Assemble paper/jbhi/submission/ from the built manuscript (run `make jbhi-paper` first).
set -euo pipefail

JB="$(cd "$(dirname "$0")" && pwd)"
SUB="$JB/submission"

need() {
  if [[ ! -f "$1" ]]; then
    echo "missing required file: $1" >&2
    exit 1
  fi
}

need "$JB/main.pdf"
need "$JB/main.tex"
need "$JB/cover_letter.md"
need "$JB/figures/lead_time_distribution.pdf"

rm -rf "$SUB/figures" "$SUB/source" "$SUB/portal_metadata"
mkdir -p "$SUB/figures" "$SUB/source/figures" "$SUB/portal_metadata"

pandoc "$JB/cover_letter.md" -o "$SUB/01_cover_letter.pdf" \
  --pdf-engine=pdflatex -V geometry:margin=0.8in -V fontsize=10pt -V pagestyle=empty
cp "$JB/main.pdf" "$SUB/02_manuscript.pdf"

(cd "$JB" && pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$SUB" \
  competing_interests.tex >/dev/null)
mv "$SUB/competing_interests.pdf" "$SUB/04_conflict_of_interest.pdf"
rm -f "$SUB"/competing_interests.{aux,log,out}

cp "$JB/figures/lead_time_distribution.pdf" "$SUB/figures/Figure2_lead_time_distribution.pdf"
cp "$JB/figures/lead_time_distribution.png" "$SUB/figures/Figure2_lead_time_distribution.png"

cp "$JB/main.tex" "$SUB/source/main.tex"
cp "$JB/figures/lead_time_distribution.pdf" "$SUB/source/figures/"
(cd "$SUB/source" && zip -qr ../03_latex_source.zip main.tex figures)
rm -rf "$SUB/source"

python3 - "$JB/main.tex" "$SUB/portal_metadata" <<'PY'
import re
import sys
from pathlib import Path

tex = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])


def plain(s: str) -> str:
    s = s.replace("\\\\", " ").replace("~", " ").replace("--", "–")
    s = re.sub(r"\$\\geq\$", "≥", s)
    s = s.replace("\\%", "%").replace("\\,", " ")
    s = re.sub(r"\\[A-Za-z]+\*?(?:\[[^]]*\])?\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[A-Za-z]+", "", s)
    s = s.replace("{", "").replace("}", "").replace("$", "")
    return re.sub(r"\s+", " ", s).strip()


title = re.search(r"\\title\{(.*?)\}\n", tex, re.DOTALL).group(1)
abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.DOTALL).group(1)
keywords = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", tex, re.DOTALL).group(1)

(out / "title.txt").write_text(plain(title) + "\n")
abstract_text = plain(abstract)
(out / "abstract.txt").write_text(abstract_text + "\n")
(out / "keywords.txt").write_text(
    "\n".join(k.strip() for k in plain(keywords).split(",")) + "\n"
)
(out / "article_type.txt").write_text("Regular Paper\n")
(out / "word_count.txt").write_text(f"Abstract: {len(abstract_text.split())} words\n")
PY

awk '/\\section\*\{Data and Code Availability\}/{f=1;next} /\\section\*/{f=0} f' "$JB/main.tex" \
  | tr '\n' ' ' | sed -e 's/\\url{\([^}]*\)}/\1/g' -e 's/  */ /g' -e 's/^ //' \
  > "$SUB/portal_metadata/data_code_availability.txt"
echo >> "$SUB/portal_metadata/data_code_availability.txt"

echo "Assembled $SUB"
find "$SUB" -type f | sort
