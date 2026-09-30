# JAMIA Open Submission Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a scientifically consistent, reproducible, journal-formatted JAMIA Open Research and Applications submission package and rebuilt manuscript PDF.

**Architecture:** Preserve the original frozen study artifacts, derive a new versioned reporting sidecar from the locked setB replay, and make the manuscript consume only versioned generated tables. Separate the four-table main manuscript from supplementary methods/results, while keeping all clinical claims explicitly retrospective and non-validated.

**Tech Stack:** Python 3.11+, pytest, LaTeX/pdfTeX, BibTeX, frozen JSON sidecars, Poppler rendering.

**Spec:** `paper/jamiaopen/SUBMISSION_CHECKLIST.md` plus the readiness findings recorded in the 2026-09-07 review of `paper/main.pdf`.

## Global Constraints

- Prototype only: synthetic/public de-identified data, not clinically validated, not FDA-cleared, and not suitable for patient care.
- Do not retune governance on `training_setB`.
- Never replace a frozen study artifact in place; create a new version and preserve existing hashes.
- Keep the LLM outside the scoring, governance, and alert paths.
- Research and Applications limits: 4,000 main-text words, 250-word structured abstract, 200-word lay summary, 4 main tables, 6 main figures, double-spaced submission.
- Preserve unrelated working-tree changes and the existing Figure 1 layout edits in `paper/main.tex`.

---

### Task 1: Versioned reporting sidecar and regression guarantees

**Files:**
- Modify: `eval/challenge2019/paper_analyses.py`
- Modify: `eval/challenge2019/test_metrics.py`
- Modify: `eval/manuscript/test_generate_paper_tables.py`
- Create: `eval/challenge2019/frozen/holdout_primary_window_m12_p6.v3.json`

**Interfaces:**
- Consumes: locked setB stay rows from `run_challenge2019_eval(..., include_stay_rows=True)`.
- Produces: a v3 holdout sidecar containing co-primary Challenge utility, cohort denominators, stay-level false-positive/PPV fields, alert rates per patient-day, and lead-time quartiles.

- [ ] Add failing tests requiring the v3 reporting fields and preserving the v2 artifact.
- [ ] Run `pytest -q eval/challenge2019/test_metrics.py eval/manuscript/test_generate_paper_tables.py` and record the expected missing-field failure.
- [ ] Extend `_metrics_card()` and the holdout sidecar builder without changing scoring or governance behavior.
- [ ] Evaluate locked setB without retuning and write a new v3 artifact; never pass `--write-frozen` because that overwrites older frozen files.
- [ ] Rerun the focused tests and verify the new reporting contract passes.

### Task 2: Four-table manuscript and supplementary evidence

**Files:**
- Modify: `eval/manuscript/generate_paper_tables.py`
- Modify: `paper/main.tex`
- Create: `paper/jamiaopen/supplement.tex`
- Create: `paper/jamiaopen/figure1-system-boundary.tex`
- Create: `paper/jamiaopen/figure-alt-text.md`

**Interfaces:**
- Consumes: v3 holdout, comparator, ablation, miss, timing, selection, rule-bundle, and operating-point artifacts.
- Produces: four main tables, a complete supplement, a separately uploadable Figure 1, and alt text for all figures.

- [ ] Add a failing manuscript test asserting four main tables, required supplementary selection details, an explicit threshold of 2, and no inaccurate “all emits interruptive” note.
- [ ] Run the focused manuscript test and record RED.
- [ ] Consolidate the main Results into holdout, burden/comparators, ablation, and miss-attribution tables; move timing robustness and selection/frontier material to the supplement.
- [ ] Distinguish the legacy setA selection estimand (88.4%/37.7%) from the post-freeze primary-window replay (87.6%/32.5%).
- [ ] Report Challenge utility and the additional burden statistics from the v3 sidecar.
- [ ] Document the complete 23-candidate selection grid location, objective, tie-breaks, rule thresholds, missingness policy, label incorporation bias, and limits of incomplete comparators.
- [ ] Export Figure 1 as a standalone LaTeX-built PDF and provide concise alt text for Figures 1-3.
- [ ] Rerun manuscript tests and verify GREEN.

### Task 3: JAMIA Open structure, title page, disclosures, and references

**Files:**
- Modify: `paper/main.tex`
- Modify: `paper/references.bib`
- Modify: `paper/jamiaopen/cover_letter.tex`
- Modify: `paper/jamiaopen/SUBMISSION_CHECKLIST.md`

**Interfaces:**
- Consumes: current JAMIA Open Research and Applications instructions and OUP AI disclosure policy.
- Produces: a double-spaced manuscript with compliant abstract, title-page metadata, section order, declarations, data/software citations, and journal-style numbered references.

- [ ] Add manuscript lint assertions for abstract/lay-summary/table limits, double spacing, keywords, word count, data/code URLs, CRediT roles, and nonempty declarations.
- [ ] Run the lint test and record RED.
- [ ] Trim the abstract below 250 words and keep the lay summary below 200 words.
- [ ] Add the known postal address, independent-researcher affiliation/location, keywords, and manuscript word count; leave only telephone and degree contingent on author confirmation.
- [ ] Rename the main opening section to Background and Significance and align required article headings.
- [ ] Add persistent repository, release/commit, and PhysioNet dataset citations; convert bibliography output to JAMIA-compatible numbered style.
- [ ] Add CRediT, ethics, funding, conflicts, acknowledgements, and a conditional OUP AI-use disclosure note for author confirmation.
- [ ] Update the cover letter and checklist so every portal asset and author-only confirmation is explicit.

### Task 4: Build, validate, and visually inspect the submission package

**Files:**
- Modify: `paper/main.pdf`
- Create: `paper/jamiaopen/supplement.pdf`
- Create: `paper/jamiaopen/figure1-system-boundary.pdf`
- Create: `docs/testing/jamia-open-submission-readiness.tdd.md`

**Interfaces:**
- Consumes: revised LaTeX, bibliography, generated tables, and versioned sidecars.
- Produces: final PDFs plus a validation evidence report.

- [ ] Regenerate paper tables and run all Challenge/manuscript tests, lint, parity, and diff checks.
- [ ] Compile the manuscript, supplement, cover letter, and standalone Figure 1 through the full LaTeX/BibTeX cycle.
- [ ] Verify word/table/figure counts, PDF integrity, absence of unresolved references/placeholders, and exact primary metrics.
- [ ] Render every PDF page to PNG and inspect typography, clipping, table breaks, captions, legends, headers, and page numbers.
- [ ] Record RED/GREEN evidence, validation commands, results, and any author-confirmation gaps in the TDD evidence report.
- [ ] Confirm all new frozen files are versioned additions and that no unrelated working-tree changes were overwritten.

