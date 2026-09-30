# MIMIC / eICU claims-and-evidence ledger

**Status:** frozen for the JBHI manuscript. The locked MIMIC-IV governance study is frozen in
`study_manifest.v3.json`; cohort flow, characteristics, MIMIC/eICU completeness, post hoc
lead-time/ICD analyses, and subgroups are frozen in `publication_aggregates.v1.json`.
**Gate:** Phase B correctness, Phase C infrastructure, and the full MIMIC Stage B run are complete.
The v2 manifest was superseded, not edited, because its legacy `fixture` and regeneration fields
did not describe the indexed full-cohort execution. See
[`docs/research/jbhi-submission.md`](jbhi-submission.md) for the publication claim boundary.

## How to read a row

Each claim row maps one proposed paper sentence to:

- **class** — `eng` (engineering characterization), `analytical` (analytical
  concordance/validation), `prohibited` (clinical claim that must not appear);
- **dataset / split / metric** — what the evidence must be computed on;
- **run / artifact / hash** — the regenerating command, output artifact, and its
  SHA-256 when one exists; `pending` means no run exists yet.

## Claims ledger

| ID | Proposed claim | Class | Dataset | Split | Metric | Run | Artifact | Hash | Status |
|---|---|---|---|---|---|---|---|---|---|
| GATE-0 | "Phase B correctness and Phase C infrastructure are integrated" | eng | — | — | — | — | — | — | **TRUE on 2026-09-05**; merged review baseline `90e4ded` |
| C1 | Shared alert governance reduces interruptive alert volume vs threshold-only scoring while preserving in-window governed detection | analytical | MIMIC-IV 3.1 credentialed | test (anchor-year-group) | PE-1 governed sensitivity, PE-2 interruptive reduction ratio, stay bootstrap CIs | `python -m eval.mimic_study.stage_b_run` | `eval/mimic_study/frozen/study_manifest.v3.json` | `f744672a…8869` | **Frozen** — v3 corrects provenance metadata only and retains v2 numerical sections; 98.49% governed sensitivity (95% CI 98.15–98.81); interruptive ratio 7.67% (95% CI 7.54–7.79) |
| C2 | Episode arbitration yields one actionable episode instead of alert floods | eng | demo-schema fixtures | — | episode vs alert counts | `python -m eval.mimic_study.study run` | `eval/mimic_study/frozen/study_manifest.v1.json` | `e4998934…c798a73` (demo) | engineering done (demo schema only) |
| C3 | Adding an indicator is a plugin/bundle task | eng | — | — | CURIE-010/011/013 gates | `make parity` | rule registry + plugin | — | engineering done |
| C4 | Availability-time replay has no future leakage | eng | demo-schema fixtures | — | CURIE-015 leakage tests | `pytest -q eval/mimic_harness/` | `eval/mimic_harness/test_harness.py` | — | engineering done (demo schema) |
| COH-1 | Cohort flow: 94,458 source stays → 85,041 protocol stays (v2 rule) → 75,475 in dev/cal/test; v1 audit rule (84,855) reconciled exactly (+186 under v2) | analytical | MIMIC-IV 3.1 credentialed | all splits | counts per exclusion step | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen** |
| COH-2 | ESRD (5,567 stays), comfort-care (13,042 stays), OR-transfer (71 stays) handling is declared and counted | analytical-audit | MIMIC-IV 3.1 credentialed | cohort-wide | subgroup flags | same as COH-1 | same as COH-1 | same | audit-only, not frozen |
| COH-3 | Temporal split assignment by ICU intime | analytical | MIMIC-IV 3.1 credentialed | dev/cal/test | — | `eval/mimic_study/cohort_flow.py --protocol-version v2` | `eval/mimic_study/frozen/protocol.v2.json` | pending full-data run | **v1 calendar split suspended; v2 anchor_year_group protocol frozen** |
| COM-1 | SOFA input observation rates (cohort-wide) and final-score component missingness (seeded 8,000-stay sample) | analytical | MIMIC-IV 3.1 credentialed | cohort-wide / n=8000 seed 42 | per-component rates | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen** (source audit SHA-256s recorded) |
| COM-2 | Pressor known-vs-unknown dose rows (685,045 known; 31,020 unknown, 30,559 units/h) | analytical | MIMIC-IV 3.1 credentialed | cohort-wide | unit/dose counters | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen** |
| COM-3 | Source-to-index row reconciliation (chartevents/labevents) | eng | MIMIC-IV 3.1 credentialed | first-25 stays | row-identity match | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen** (all match) |
| LAB-1 | MIMIC Sepsis-3 / KDIGO labels generated from pinned, versioned definitions | analytical | MIMIC-IV 3.1 credentialed | — | onset events | `scripts/materialize_mimic_labels.py` | protected operator artifact + `eval/mimic_study/labels/frozen/mimic_code_pin.v1.json` | aggregate label hash `9ed57505…6769` | **Done for Stage B**; patient-level label artifact remains uncommitted under the DUA |
| CON-1 | Component/stay/event-time/window concordance vs pinned reference implementation, disagreements classified (unit/timing/missingness/mapping/definition) | analytical | MIMIC-IV 3.1 credentialed | — | concordance summary | `eval/mimic_study/comparators/` | pending run | — | Blocked on LAB-1 + Phase C |
| GOV-1 | Naive vs governed vs interruptive burden and watch-vs-page separation | analytical | MIMIC-IV 3.1 credentialed | locked test | PE-1/PE-2 + burden endpoints | `python -m eval.mimic_study.stage_b_run` | `eval/mimic_study/frozen/study_manifest.v3.json` | `f744672a…8869` | **Frozen**; 7.67% is interruptive/governed-policy emissions divided by naive interruptive emissions, while all governed records are 18.03% of raw crossings |
| ROB-1 | Pre-specified robustness: urine grace windows, detection windows, partial-score policy, pressor unknown-dose handling, FiO2/PaO2 preference, SpO2 fallback, ESRD/comfort/OR variants, split stability, bootstrap seed 42 | analytical | MIMIC-IV 3.1 credentialed | test (pre-specified only) | effect direction + CIs | pending | pending | pending | Blocked; scaffolding in `eval/mimic_study/bootstrap.py` (seed 42, 1000 replicates) |
| EICU-1 | eICU completeness/portability analysis | analytical-audit | eICU-CRD demo | demo smoke (50 stays) | component missing rates | `python -m eval.mimic_study.eicu_audit` | `data/audit/eicu_portability_audit.json` | `6741cef4…59959e` | audit-only, not frozen; explicitly not clinical validation |
| EICU-2 | eICU final-score component missingness on the protocol-seeded n=8000 sample | analytical | eICU-CRD v2.0 | n=8000, seed 42 | component missing rates | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen**; respiration 59.7%; completeness only, not clinical validation |
| PH-1 | Post hoc: lead ≥2 h reduces governed sensitivity to 54.43% (53.02–55.79) and interruptive to 10.89% | analytical | MIMIC-IV 3.1 credentialed | locked test | stay bootstrap CI | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen**, post hoc |
| PH-2 | Post hoc: ICD discharge-code label sensitivity (2,249 code-positive; any governed alert 97.69%; code-negative 80.46%) | analytical | MIMIC-IV 3.1 credentialed | locked test | stay bootstrap CI | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen**, post hoc; not independent validation |
| SUB-1 | Descriptive sex/age subgroup scorecards | analytical | MIMIC-IV 3.1 credentialed | locked test | sensitivity, burden | `make mimic-publication-aggregates` | `eval/mimic_study/frozen/publication_aggregates.v1.json` | `290f06d1…2a104` | **Frozen**, descriptive; cells <11 suppressed |
| NON-1 | Clinical SOFA accuracy / superiority to NEWS/qSOFA | prohibited | — | — | — | — | — | — | must not appear |
| NON-2 | Improved outcomes / mortality prediction / treatment benefit | prohibited | — | — | — | — | — | — | must not appear |
| NON-3 | Clinical validation on MIMIC or eICU | prohibited | — | — | — | — | — | — | must not appear; eICU is completeness/portability only |
| NON-4 | FDA/SaMD readiness or production readiness | prohibited | — | — | — | — | — | — | must not appear |
| NON-5 | "External validation from unlabeled dumps or demo data" | prohibited | — | — | — | — | — | — | must not appear |
| NON-6 | MIMIC/eICU as a second confirmation of the Challenge 2019 setB governance claim | prohibited | — | — | — | — | — | — | must not appear; Challenge 2019 is a separate frozen cohort |

## Integration-gate evidence (2026-09-05)

- Review baseline `90e4ded` contains the merged Phase B correctness, Phase C indexed
  replay, and literature-audit work. The repository worktree is clean.
- Phase B blocker B1 (MIMIC `rateuom`) is wired into
  `ingestion/adapters/mimic/extract.py`; the typed conversion policy and audit
  remain in `ingestion/adapters/mimic/vasopressors.py`, with unknown units and
  missing rates handled explicitly.
- The eICU n=8000 result above is an audit measurement, not clinical validation and
  not a frozen study result. MIMIC-IV labels and comparator runs remain
  outstanding; protocol v2 now resolves the prior temporal-split blocker.
- The baseline documentation's 53.1% eICU respiration figure is reproducible only
  with the pre-correction scorer. The current scorer uses Rice 2007 S/F→P/F
  imputation and fails closed above SpO₂ 97%, yielding 59.725%. These are not
  interchangeable estimates.

## Regeneration commands

```bash
python -m eval.mimic_study.cohort_flow --protocol-version v2 --json-out data/audit/mimic_cohort_flow.json
python -m eval.mimic_study.index_replay export-rows --protocol-version v2 --index-dir data/index/mimic-iv --limit 0 --json-out data/audit/mimic_study_rows.v2.json
python -m eval.mimic_study.completeness_audit --json-out data/audit/mimic_completeness_audit.json
python -m eval.mimic_study.eicu_audit --json-out data/audit/eicu_portability_audit.json
CURIE_EICU_DIR=/path/to/eicu-crd-v2.0 python -m eval.mimic_study.completeness_check --dataset eicu --limit 8000 --seed 42 --batch-size 200 --json-out data/audit/eicu_sofa_missingness_n8000.json
python -m pytest -q                                  # repository checks
python -m eval.parity.gate                           # PARITY_OK=true fixtures=43 mismatches=0
make flink-test                                      # passed via Maven/Docker
```

Artifact hashes are SHA-256 of the JSON files in `data/audit/`. All audit outputs
carry `"status": "AUDIT_ONLY_NOT_FROZEN"`; paper-facing values come from
`publication_aggregates.v1.json` (`make mimic-publication-aggregates`), which records those
SHA-256s and refuses to overwrite an existing version.
