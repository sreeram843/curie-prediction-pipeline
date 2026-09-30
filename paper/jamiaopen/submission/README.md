# JAMIA Open submission package

**Article type:** Research and Applications  
**Portal:** Oxford University Press ScholarOne for *JAMIA Open*  
**Instructions source:** [General Instructions](https://academic.oup.com/jamiaopen/pages/General_Instructions) (verify live page at submit time; this folder mirrors the Research and Applications upload set)

Official page fetch can be Cloudflare-blocked from automation. Limits used here match the journal’s Research and Applications rules as documented in-repo and in secondary mirrors of the same instructions:

| Limit | Requirement | This package |
|---|---|---|
| Main text | ≤ 4,000 words | 1,723 |
| Structured abstract | ≤ 250 words; Objectives / Materials and Methods / Results / Discussion / Conclusion | in manuscript + `portal_metadata/abstract.txt` |
| Lay summary | mandatory for JAMIA Open (≤ 200 words) | in manuscript + `portal_metadata/lay_summary.txt` |
| Tables / figures | ≤ 4 tables, ≤ 6 figures | 4 tables in manuscript; 3 separate figure files |
| Cover letter | required; disclose AI use; related papers / prior reviews | `01_cover_letter.pdf` |
| Supplementary | optional but used here for selection grid / extra tables | `03_supplementary_material.pdf` |
| Figure alt text | under each figure legend in the manuscript | also `portal_metadata/figure_alt_text.txt` for portal paste |

## Upload map (ScholarOne)

Upload these files in roughly this order:

1. **Cover letter** → `01_cover_letter.pdf`
2. **Main document / manuscript** → `02_manuscript_main.pdf`  
   (PDF is acceptable for review; if the portal insists on Word, export from this PDF or ask for a `.docx` conversion pass.)
3. **Supplementary material** → `03_supplementary_material.pdf`
4. **Figure 1** → `figures/Figure1_system_boundary.pdf` (PNG also provided)
5. **Figure 2** → `figures/Figure2_detection_burden.pdf` (PNG also provided)
6. **Figure 3** → `figures/Figure3_timing_robustness.pdf` (PNG also provided)

Prefer **PDF** for vector figures when the portal allows it; use the matching **PNG** if the form requires raster only.

## Paste-from metadata

Use files in `portal_metadata/` when the portal asks for free-text fields:

| Portal field | File |
|---|---|
| Title | `title.txt` |
| Keywords | `keywords.txt` |
| Structured abstract | `abstract.txt` |
| Lay / patient-facing summary | `lay_summary.txt` |
| Figure alt text | `figure_alt_text.txt` |
| Article type | `article_type.txt` |
| Data / code availability | `data_code_availability.txt` |

## Peer review model

*JAMIA Open* uses **single-blind** review. Author name, affiliation, ORCID, and correspondence on the title page are expected.

## Author confirmations still required

See `AUTHOR_TODO.md`. Do not submit until telephone (if required), public GitHub status, ethics wording, and AI disclosure beyond Codex are confirmed.

## Rebuild this folder

From `paper/`:

```bash
# refresh PDFs first if sources changed
pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
(cd jamiaopen && pdflatex cover_letter.tex && pdflatex supplement.tex && pdflatex figure1-system-boundary.tex)
bash jamiaopen/assemble_submission.sh
```
