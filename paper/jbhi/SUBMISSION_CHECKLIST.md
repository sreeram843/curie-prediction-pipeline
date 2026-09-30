# IEEE JBHI submission checklist

**Current verdict:** Manuscript and package complete. Every numerical statement is backed by a
frozen sidecar and checked by `eval/manuscript/test_jbhi_submission.py`. Only the author/portal
actions under "Author actions before upload" remain.

## Scientific separation

- [x] Primary dataset and scientific question differ from the companion IJMI submission
  (IJMEDI-S-26-06829, PhysioNet Challenge 2019).
- [x] No Challenge 2019 result is used as JBHI evidence.
- [x] Companion manuscript title, journal, manuscript ID, status, and non-overlap explanation are in
  the manuscript ("Relation to the companion manuscript") and cover letter.
- [ ] Author judgment: submit while IJMI review is ongoing (content is distinct and disclosed) or
  wait for the IJMI decision.

## Evidence and claims

- [x] MIMIC-IV protocol v2, operating point v2, label pin, locked test metrics, bootstrap intervals,
  and miss count exist as frozen artifacts.
- [x] Provenance-corrected manifest version published; v2 preserved unchanged
  (`study_manifest.v3.json`, hash `f744672a…8869`).
- [x] MIMIC cohort flow, characteristics, and completeness frozen in
  `eval/mimic_study/frozen/publication_aggregates.v1.json` (content hash `290f06d1…2a104`).
- [x] eICU-CRD 2.0 completeness for the seeded 8,000-stay sample frozen in the same sidecar with the
  source audit SHA-256.
- [x] Lead-time-gated and ICD label-sensitivity analyses frozen and labeled post hoc.
- [x] Every table cell and numerical sentence maps to a frozen JSON field (tests check cohort flow,
  characteristics, primary metrics, ablations, post hoc analyses, and subgroup rows).
- [ ] Repository release/DOI is public and contains the cited aggregate artifacts and commands
  (author action).

## Scientific depth for peer review

- [x] Cohort-flow table with every exclusion and split; the 84,855 vs 85,041 difference is
  reconciled exactly (186 stays, v1 rule replicated).
- [x] System/data-flow figure (Fig. 1) shows availability time, score output, passive governance,
  interruptive routing, the no-language-model boundary, and offline-only reference labels.
- [x] Prespecified governance ablations reported (Table VI).
- [x] Lead-time sensitivity (Fig. 2, Table VII) and ICD label sensitivity with label-negative alert
  rates address construct overlap.
- [x] Cohort characteristics (Table III) and descriptive sex/age subgroup scorecards (Table VIII),
  aggregate-only with small-cell suppression.
- [x] Related work compares EHR SOFA reconstruction, missing-data handling, alert
  deduplication/refractory policies, and CDS evaluation (31 references).
- [x] Novelty is stated as the combination and evaluation boundary, not as individually
  unprecedented mechanisms.
- [ ] Optional but recommended: clinical informatics/critical-care reviewer read-through.

## Manuscript

- [x] Abstract is no more than 250 words.
- [x] Title states that governance was evaluated only in MIMIC-IV.
- [x] The 7.67% denominator is naive interruptive emissions, not all threshold crossings.
- [x] No "preregistered," "trustworthy," affirmative "clinical validation," production-ready,
  outcome-benefit, diagnostic-accuracy, or regulatory-readiness claim appears.
- [x] eICU-CRD is described only as an extraction/completeness audit.
- [x] Exact PhysioNet dataset citations and DOIs are included.
- [x] No TODO, `%AUTHOR`, placeholder, or unsupported superlative remains in `main.tex` or the
  cover letter.

## IEEE and author declarations

- [x] Ethics statement explains why independent review was not required (secondary analysis of
  deidentified PhysioNet data) and states the consent basis under the source-database approvals.
- [x] AI disclosure names OpenAI Codex, the Cursor coding agent, and Claude Code, the affected work
  (code, figure scripts, manuscript drafting/LaTeX), and author verification.
- [x] Funding (none), competing interests (none), author contribution, data/code availability, and
  ORCID are stated.
- [x] Traditional (non-open-access) route chosen; select it in the IEEE portal.

## Package quality

- [x] IEEE journal template; 7 pages (within the 8-page regular-paper allowance).
- [x] Visual inspection: no clipping, overflow, illegible table, orphan heading, or blank page.
- [x] Fonts embedded; no unresolved references.
- [x] `make jbhi-paper` regenerates Fig. 2 from the sidecar and rebuilds the PDF.
- [x] Clean upload directory at `paper/jbhi/submission/` with portal metadata.

## Author actions before upload

See `paper/jbhi/submission/AUTHOR_TODO.md`.
