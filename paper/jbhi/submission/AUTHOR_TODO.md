# Author actions before IEEE JBHI (IEEE Author Portal) submit

Confirmations recorded 2026-09-29 from the corresponding author.

- [x] Ethics: secondary analysis of deidentified PhysioNet data under DUAs; no independent review
  required; consent not applicable/waived under source-database approvals (manuscript + cover letter).
- [x] AI tools: OpenAI Codex, Cursor agent, Claude Code (manuscript Acknowledgment + cover letter).
- [x] Companion manuscript disclosed: IJMI IJMEDI-S-26-06829, under review.
- [x] Publication route: traditional (no APC).

## Before upload

- [ ] Commit and push the JBHI work (manuscript, `publication_aggregates.v1.json`, tests, scripts),
  then create a tagged GitHub release (for example `jbhi-v1`) and, optionally, a Zenodo DOI. The
  Data and Code Availability statement cites the repository and must point at content that
  already contains the sidecar.
- [ ] Decide whether to submit now (content distinct and disclosed) or after the IJMI decision.
- [ ] Re-run `pytest -q eval/manuscript/test_jbhi_submission.py eval/mimic_study/` and
  `make jbhi-paper && paper/jbhi/assemble_submission.sh` immediately before upload.
- [ ] Recheck live JBHI instructions and page charges:
  <https://www.embs.org/jbhi/> and the IEEE Author Portal fee schedule.

## In the portal (https://ieee.atyponrex.com/journal/jbhi-embs)

- [ ] Manuscript type: Regular Paper. Paste title, abstract, keywords from `portal_metadata/`.
- [ ] Paste the cover letter (`cover_letter.md`) into the portal's cover-letter text box (required);
  `01_cover_letter.pdf` can also be attached if a file slot is offered.
- [ ] Upload `02_manuscript.pdf` (review PDF); upload
  `03_latex_source.zip` if source files are requested (required at final acceptance).
- [ ] Fig. 1 is drawn in TikZ inside `main.tex`; Fig. 2 is also provided separately under
  `figures/`.
- [ ] Enter the related-manuscript disclosure (IJMEDI-S-26-06829) in the portal's prior/related
  publication field, and upload the IJMI manuscript as a "not for review" file if requested.
- [ ] Select the traditional (non-open-access) option.
- [ ] Suggested reviewers and any exclusions (portal usually asks for 3–5).
- [ ] Optional: a clinical informatics or critical-care colleague reads the manuscript before upload.

## Separate (first paper)

- [ ] Correct the Westcliff affiliation on IJMEDI-S-26-06829 in Editorial Manager.
