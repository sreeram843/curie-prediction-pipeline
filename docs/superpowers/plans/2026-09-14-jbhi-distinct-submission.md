# Distinct JBHI Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox.

**Goal:** Produce an IEEE JBHI regular-paper package that is scientifically distinct from the
JAMIA Open manuscript, numerically traceable to frozen evidence, and ready for author-only and
portal-only submission actions.

**Architecture:** Treat the manuscript as the presentation layer of a versioned evidence package.
The frozen MIMIC-IV study is the primary evaluation; cross-dataset completeness and secondary
analyses enter only after dedicated aggregate sidecars are frozen. Automated checks connect claims
in LaTeX to evidence identifiers and block prohibited wording or denominator errors.

**Tech Stack:** IEEEtran LaTeX, latexmk/pdflatex, Python/pytest, JSON frozen sidecars, Poppler PDF
rendering and inspection.

**Spec:** `docs/research/jbhi-submission.md`

**Global Constraints:** Preserve all frozen v1/v2 artifacts; never use patient-level data as a
committed artifact; never retune on test; keep the LLM off the alert path; describe the system only
as a retrospective research prototype; do not modify the JAMIA Open paper to create artificial
differences.

---

### Task 1: Establish a non-overlap and claims contract

- [x] Write the scientific-identity comparison, evidence policy, and JBHI acceptance gates in
  `docs/research/jbhi-submission.md`.
- [x] Update `docs/research/mimic-eicu-claims-ledger.md` so completed MIMIC Stage B evidence is no
  longer marked pending and audit-only results remain clearly separated.
- [x] Add `paper/jbhi/SUBMISSION_CHECKLIST.md` with evidence, ethics, related-work, formatting, and
  portal gates.

### Task 2: Repair publication provenance without changing frozen v2

- [x] Add a tested versioned migration or rerun path that produces a new MIMIC study manifest with
  accurate indexed-stream source and regeneration metadata.
- [x] Verify all numerical payloads copied from v2 are identical and record the v2 source hash.
- [x] Never edit or replace `eval/mimic_study/frozen/study_manifest.v2.json`.

### Task 3: Freeze currently audit-only publication aggregates

- [x] Freeze a MIMIC completeness/cohort-flow aggregate from the credentialed, pinned index
  (`publication_aggregates.v1.json`; cohort flow recomputed from the index, completeness from the
  hashed audit outputs).
- [x] Freeze the eICU-CRD 2.0 completeness aggregate with dataset version, sampling seed, cohort
  definition, denominator, source SHA-256, and content hash (same sidecar).
- [x] Freeze ICD-label and lead-time aggregate results (post hoc section of the same sidecar);
  reset-tolerance results are not reported.

### Task 4: Rewrite the manuscript for JBHI

- [x] Rewrite `paper/jbhi/main.tex` around the informatics method and system boundary rather than
  the Challenge 2019 benchmark narrative.
- [x] Correct cohort and alert-volume denominators, remove “preregistered,” and eliminate clinical
  validation/trustworthiness language.
- [x] Add exact dataset citations, method references, explicit ethics/consent language pending
  author confirmation, and IEEE-compliant AI disclosure.
- [x] Keep unresolved aggregate results out of the final-claim path until Task 3 passes.

### Task 5: Add manuscript evidence checks

- [x] Add tests for abstract length, prohibited wording, dataset scope, evidence identifiers,
  denominator wording, unresolved markers, and required disclosure sections.
- [x] Run the focused manuscript tests and relevant MIMIC study tests.

### Task 6: Build and visually inspect the PDF

- [x] Compile from a clean `paper/jbhi/` build.
- [x] Confirm eight pages or fewer unless overlength charges are explicitly accepted.
- [x] Render every page to images and inspect typography, clipping, tables, figures, references,
  and blank space.
- [x] Check embedded fonts and absence of LaTeX warnings that affect publication quality.

### Task 7: Assemble submission materials

- [x] Draft a cover letter that states the technical contribution and discloses the related
  companion manuscript (IJMI IJMEDI-S-26-06829) with a concrete non-overlap paragraph.
- [x] Produce a clean submission directory containing only portal files
  (`paper/jbhi/assemble_submission.sh` → `paper/jbhi/submission/`).
- [x] Record author-confirmation items: ethics, AI systems, related-manuscript status, publication
  route, author metadata, reviewers, and conflicts.
- [ ] Recheck the live JBHI portal instructions immediately before upload.

### Task 8: Final verification

- [x] Run `pytest -q`, `ruff check .`, `git diff --check`, and `make flink-test` (or document any
  unrelated pre-existing failures precisely). 2026-09-29: 591 tests pass; remaining `ruff` (2 import
  orders in JAMIA/Challenge test files, 1 long line in `eval/mimic_study/study.py`) and
  `git diff --check` (trailing whitespace in generated `paper/tables/*.csv`) findings predate this
  work. `make flink-test` not rerun: no Java, scorer, or governance code changed.
- [x] Compare every abstract/result/table number against its frozen sidecar.
- [x] Confirm no protected patient-level data, temporary audit outputs, or credentials entered the
  submission package.
- [x] Mark the paper ready only when every non-author gate above is green and the author decisions
  are resolved. Remaining author/portal items: `paper/jbhi/submission/AUTHOR_TODO.md`.
