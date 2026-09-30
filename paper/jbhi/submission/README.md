# IEEE JBHI upload package

Regenerate with `make jbhi-paper && paper/jbhi/assemble_submission.sh`.

| File | Portal use |
|---|---|
| `01_cover_letter.pdf` | Cover letter (from `paper/jbhi/cover_letter.md`) |
| `02_manuscript.pdf` | Main manuscript, IEEE journal template, 7 pages |
| `03_latex_source.zip` | `main.tex` + figure files (compiles standalone) |
| `04_conflict_of_interest.pdf` | Signed-style conflict-of-interest declaration (from `paper/jbhi/competing_interests.tex`) |
| `05_graphical_abstract.png` | Graphical abstract, 660 x 295 px, 300 dpi (`make_graphical_abstract.py`, numbers from frozen sidecars) |
| `06_author_consent_UNSIGNED.pdf` | JBHI Author Consent form, prefilled; sign and date by hand before upload |
| `figures/Figure2_lead_time_distribution.{pdf,png}` | Fig. 2 as a separate file |
| `portal_metadata/*.txt` | Title, abstract, keywords, article type, data/code availability, graphical abstract text |

All manuscript numbers come from `eval/mimic_study/frozen/study_manifest.v3.json` and
`eval/mimic_study/frozen/publication_aggregates.v1.json`, checked by
`eval/manuscript/test_jbhi_submission.py`. The package contains no patient-level data.
Remaining author actions: `AUTHOR_TODO.md`.
