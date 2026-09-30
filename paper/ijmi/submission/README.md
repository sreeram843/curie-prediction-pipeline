# IJMI submission package

**Journal:** International Journal of Medical Informatics (Elsevier)  
**Submit:** https://www.editorialmanager.com/ijmi  
**Guide:** https://www.sciencedirect.com/journal/international-journal-of-medical-informatics/publish/guide-for-authors  
**Article type:** Original research article  
**Fee path:** Subscription / non–open access (no APC)

## Important scope warning

IJMI prioritizes real-world clinical impact and may desk-reject purely offline
technical evaluations. This package includes a Clinical Translation Roadmap and
frames the work as CDS **alert governance** evaluation. Acceptance is not
guaranteed; if editors suggest transfer or reject for scope, consider *Applied
Clinical Informatics* (non-OA) or a Short communication after cutting to ≤1,500
words.

## Limits check (Original research)

| Requirement | Limit | This package |
|---|---|---|
| Abstract | ≤ 300 words | ~206 |
| Main text | ≤ 3,000 words | 1,723 |
| Figures | ≤ 4 | 3 |
| Tables | ≤ 5 | 4 |
| Summary table | 2–4 bullets | included |
| Highlights | 3–5 × ≤85 chars | included |

## Upload map (Editorial Manager)

1. **Cover letter** → `01_cover_letter.pdf`
2. **Manuscript** → `02_manuscript_main.pdf` (LaTeX source optional later)
3. **Highlights** → `04_highlights.txt` (separate editable file; required/encouraged)
4. **Summary table** → paste `05_summary_table.txt` where EM asks, or upload as supporting file
5. **Figures (separate)** → `figures/Figure1_*.pdf`, `Figure2_*.pdf`, `Figure3_*.pdf`
6. **Supplementary material** → `03_supplementary_material.pdf`
7. **Clinical Translation Roadmap** → upload `06_clinical_translation_roadmap.txt` as supplementary/supporting
8. **ML checklist note** → `07_ml_checklist_note.txt` (deterministic rules; checklist N/A)

When EM asks about Open Access: choose **subscription / do not publish OA** (no APC).

## Rebuild

```bash
cd paper
pdflatex main.tex && bibtex main && pdflatex main.tex && pdflatex main.tex
(cd ijmi && pdflatex cover_letter.tex)
bash ijmi/assemble_submission.sh
```
