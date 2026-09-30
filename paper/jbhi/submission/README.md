# IEEE JBHI upload package

Regenerate with `make jbhi-paper && paper/jbhi/assemble_submission.sh`.

| File | Portal use |
|---|---|
| `01_cover_letter.pdf` | Cover letter (from `paper/jbhi/cover_letter.md`) |
| `02_manuscript.pdf` | Main manuscript, IEEE journal template, 7 pages |
| `03_latex_source.zip` | `main.tex` + figure files (compiles standalone) |
| `figures/Figure2_lead_time_distribution.{pdf,png}` | Fig. 2 as a separate file |
| `portal_metadata/*.txt` | Title, abstract, keywords, article type, data/code availability |

All manuscript numbers come from `eval/mimic_study/frozen/study_manifest.v3.json` and
`eval/mimic_study/frozen/publication_aggregates.v1.json`, checked by
`eval/manuscript/test_jbhi_submission.py`. The package contains no patient-level data.
Remaining author actions: `AUTHOR_TODO.md`.
