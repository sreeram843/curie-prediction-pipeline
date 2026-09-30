# JBHI manuscript scope and submission specification

**Target:** IEEE Journal of Biomedical and Health Informatics (JBHI), regular paper  
**Working directory:** `paper/jbhi/`  
**Status:** manuscript and package complete; author/portal actions remain
(`paper/jbhi/submission/AUTHOR_TODO.md`)  
**Last checked:** 2026-09-29

The companion benchmark paper was submitted to the *International Journal of Medical Informatics*
(IJMEDI-S-26-06829, under review) rather than JAMIA Open; "JAMIA Open" below refers to that same
benchmark manuscript.

## Scientific identity

The JBHI paper is a distinct informatics study, not an IEEE-formatted version of the JAMIA Open
submission.

| Dimension | JAMIA Open manuscript | JBHI manuscript |
|---|---|---|
| Primary question | Does a deterministic governance layer reduce alert burden on the PhysioNet Challenge 2019 benchmark? | How do explicit missingness semantics and a versioned routing policy behave when SOFA is reconstructed from longitudinal ICU EHR data? |
| Primary data | Challenge 2019 setA/setB | MIMIC-IV 3.1; eICU-CRD 2.0 only for a secondary completeness audit |
| Main contribution | Benchmark evaluation and governance ablations | Biomedical-informatics implementation boundary: availability-time scoring, provenance, abstention, routing, and locked real-EHR evaluation |
| Primary evidence | Frozen Challenge 2019 holdout artifacts | Frozen MIMIC-IV protocol, operating point, label pin, and test manifest |
| External analysis | Cross-hospital Challenge holdout | eICU extraction/completeness only; no outcome or governance validation |
| Prohibited overlap | Reusing the same tables, figures, result narrative, or central claim | Presenting Challenge 2019 as evidence in the JBHI study |

The cover letter and submission form must disclose the related JAMIA Open manuscript and explain
the distinctions above. The two manuscripts must not be under concurrent consideration if their
scope is judged substantively overlapping. IEEE's recycling policy requires disclosure of related
submitted or published work and a clear account of how the new paper differs.

## JBHI positioning

JBHI describes its scope as original biomedical and health informatics work at the intersection of
information and communication technologies with health and healthcare. This manuscript should
therefore foreground the technical method and its measurable behavior:

1. availability-time event reconstruction that prevents future leakage;
2. deterministic, rule-versioned SOFA computation with explicit `partial` and
   `insufficient_data` states rather than silent normal-value imputation;
3. separation of score production, passive alerting, and interruptive routing;
4. locked development/calibration/test evaluation with stay-level uncertainty;
5. failure analysis showing the difference between loose-window detection and actionable lead
   time.

This is analytical evaluation of a research prototype. It is not clinical validation, diagnostic
validation, evidence of improved outcomes, a prospective evaluation, or a claim of deployment or
regulatory readiness.

## Evidence policy

Every number in the main manuscript must resolve to a versioned, reviewable artifact. Patient-level
MIMIC-IV and eICU-CRD data remain under the PhysioNet data-use agreements and are not distributed.

### Evidence currently suitable for the paper

- `eval/mimic_study/frozen/protocol.v2.json`: frozen design and endpoints.
- `eval/mimic_study/frozen/operating_point.v2.json`: calibration-selected operating point.
- `eval/mimic_study/frozen/study_manifest.v3.json`: locked MIMIC-IV test metrics, bootstrap
  intervals, miss count, dataset/index pin, label hash, and ablations (provenance-corrected
  successor to v2, which is preserved unchanged).
- `eval/mimic_study/frozen/publication_aggregates.v1.json` (`make mimic-publication-aggregates`):
  cohort flow with v1/v2 reconciliation, split characteristics, MIMIC-IV cohort-wide and
  MIMIC-IV/eICU-CRD 8,000-stay completeness, post hoc lead-gated and ICD label-sensitivity
  analyses, and descriptive subgroups. Records source SHA-256s and refuses to overwrite.
- `eval/mimic_study/labels/frozen/mimic_code_pin.v1.json` and `icd_sepsis_codes.v1.json`:
  reference-label and ICD-code pins.
- versioned rule bundles and parity fixtures: deterministic implementation evidence.

`eval/manuscript/test_jbhi_submission.py` checks the manuscript numbers against these sidecars.
Reset-tolerance results are not reported.

## Manuscript acceptance gates

- The title and abstract identify MIMIC-IV as the governance evaluation and eICU-CRD as
  completeness-only.
- The abstract is at most 250 words and contains no unsupported clinical or deployment claim.
- The denominator for the 7.7% result is always `interruptive alerts / naive interruptive alerts`;
  governed alerts are 18.0% of all naive threshold-crossing alerts.
- “Prespecified and frozen before test evaluation” replaces “preregistered” unless an external,
  date-stamped registration is supplied.
- Observation rate is not described as score validity or trustworthiness.
- ICD discharge codes are a label-sensitivity analysis, not independent clinical validation and
  not proof against circularity.
- eICU-CRD supports extraction/completeness portability only.
- Ethics text names the oversight or exemption basis and explains the consent basis, as required by
  IEEE policy.
- The acknowledgments identify any AI system that generated manuscript text, figures, or code and
  identify the affected sections and level of use. Grammar-only editing may be disclosed
  voluntarily.
- Exact MIMIC-IV 3.1 and eICU-CRD 2.0 PhysioNet citations and DOIs are included.
- The repository release cited in the paper contains the manuscript, aggregate sidecars, hashes,
  tests, and reproduction commands; no public-availability claim precedes that release.
- The regular-paper PDF is eight IEEE pages or fewer unless the author accepts overlength charges.
- The final PDF is visually inspected page by page, fonts are embedded, hyperlinks work, tables and
  figures are legible in two columns, and no TODO/`AUTHOR` marker remains.

## Author decisions

Resolved (2026-09-29): no IRB review (secondary analysis of deidentified PhysioNet data; consent
not applicable/waived under source approvals); AI systems OpenAI Codex, Cursor agent, Claude Code;
companion paper at IJMI (IJMEDI-S-26-06829, under review); traditional publication route.

Open: public release/DOI, suggested reviewers and exclusions, and whether to submit during the
IJMI review. See `paper/jbhi/submission/AUTHOR_TODO.md`.

## Peer-review depth

The 7-page manuscript adds a cohort-flow table, a system/data-flow figure, ablations, lead-time and
label-sensitivity evidence, cohort/subgroup characterization, and a 31-reference comparison with
prior EHR SOFA and alert-governance work. Low interruptive precision and the high absolute
interruption rate remain prominent as design findings.

## Official sources checked

- JBHI scope: <https://www.embs.org/jbhi/articles/jbhi/>
- IEEE submission, recycling, human-subject, and AI policies:
  <https://journals.ieeeauthorcenter.ieee.org/become-an-ieee-journal-author/publishing-ethics/guidelines-and-policies/submission-and-peer-review-policies/>
- 2026 IEEE publication charge schedule: eight regular JBHI pages before mandatory overlength
  charges; verify again in the submission portal.
- MIMIC-IV 3.1: <https://physionet.org/content/mimiciv/3.1/>, DOI
  `10.13026/kpb9-mt58`.
- eICU-CRD 2.0: <https://physionet.org/content/eicu-crd/2.0/>, DOI
  `10.13026/C2WM1R`.
