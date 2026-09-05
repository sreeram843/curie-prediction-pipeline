# MIMIC / eICU claims-and-evidence ledger

**Status:** scaffolding — no frozen study numbers exist yet.
**Gate:** Phase B (correctness) and Phase C (infrastructure) are **not integrated** on
`codex/review-fixes` as of 2026-09-05 (see
[`docs/superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md`](../../superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md)).
Until the gate passes, every number in this worktree is **audit-only** (written under
gitignored `data/audit/`, labeled `AUDIT_ONLY_NOT_FROZEN`), and no frozen artifact is
created or replaced.

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
| GATE-0 | "Phase B correctness and Phase C infrastructure are integrated" | eng | — | — | — | — | — | — | **FALSE on 2026-09-05** (see gate section below) |
| C1 | Shared alert governance reduces interruptive alert volume vs threshold-only scoring while preserving in-window detection | analytical | MIMIC-IV 3.1 credentialed | test (temporal) | PE-1 governed sensitivity, PE-2 interruptive reduction ratio, stay bootstrap CIs | pending | `eval/mimic_study/frozen/` (new version) | pending | **Blocked** — splits inapplicable (date shift); B/C not integrated |
| C2 | Episode arbitration yields one actionable episode instead of alert floods | eng | demo-schema fixtures | — | episode vs alert counts | `python -m eval.mimic_study.study run` | `eval/mimic_study/frozen/study_manifest.v1.json` | `e4998934…c798a73` (demo) | engineering done (demo schema only) |
| C3 | Adding an indicator is a plugin/bundle task | eng | — | — | CURIE-010/011/013 gates | `make parity` | rule registry + plugin | — | engineering done |
| C4 | Availability-time replay has no future leakage | eng | demo-schema fixtures | — | CURIE-015 leakage tests | `pytest -q eval/mimic_harness/` | `eval/mimic_harness/test_harness.py` | — | engineering done (demo schema) |
| COH-1 | Cohort flow: 84,855 stays survive the frozen adult/first-stay/LOS≥4h/valid-time filters, with denominators at each step | analytical-audit | MIMIC-IV 3.1 credentialed | cohort-wide (no split) | counts per exclusion step | `python -m eval.mimic_study.cohort_flow` | `data/audit/mimic_cohort_flow.json` | `07e0f207…9aede` | audit-only, not frozen |
| COH-2 | ESRD (5,567 stays), comfort-care (13,042 stays), OR-transfer (71 stays) handling is declared and counted | analytical-audit | MIMIC-IV 3.1 credentialed | cohort-wide | subgroup flags | same as COH-1 | same as COH-1 | same | audit-only, not frozen |
| COH-3 | Temporal split assignment by ICU intime | analytical | MIMIC-IV 3.1 credentialed | dev/cal/test | — | — | — | — | **SUSPENDED** — v3.1 shifts dates independently per subject (deidentified years 2100–2200); frozen v1 calendar ranges are inapplicable; only `anchor_year_group` (3-year buckets) preserves approximate order; protocol amendment required |
| COM-1 | SOFA component observation rates, complete vs partial coverage, first-ICU-day missingness, event-time distribution, runtime/peak RSS | analytical-audit | MIMIC-IV 3.1 credentialed | cohort-wide | per-component rates | `python -m eval.mimic_study.completeness_audit` | `data/audit/mimic_completeness_audit.json` | pending (run in progress) | audit-only, not frozen |
| COM-2 | Pressor unit distribution and known-vs-unknown dose rates | analytical-audit | MIMIC-IV 3.1 credentialed | cohort-wide | unit/dose counters | `audit_inputevents_pressors` | `data/audit/mimic_pressor_unit_audit.json` | `fcf703d5…113` | audit-only, not frozen |
| COM-3 | Source-to-index row reconciliation (chartevents/labevents) | eng-audit | MIMIC-IV 3.1 credentialed | first-25 stays | row-identity match | `python -m eval.mimic_study.completeness_audit` | `data/audit/mimic_completeness_audit.json` | pending | audit-only, not frozen |
| LAB-1 | MIMIC Sepsis-3 / KDIGO labels generated from pinned, versioned definitions | analytical | MIMIC-IV 3.1 credentialed | — | onset events | `eval/mimic_study/labels/` | `eval/mimic_study/labels/sources.json` | mimic-code pin `303d26c6…` | **Not implemented** — SQL sources pinned + sha256-verified; generation blocked on Phase C |
| CON-1 | Component/stay/event-time/window concordance vs pinned reference implementation, disagreements classified (unit/timing/missingness/mapping/definition) | analytical | MIMIC-IV 3.1 credentialed | — | concordance summary | `eval/mimic_study/comparators/` | pending run | — | Blocked on LAB-1 + Phase C |
| GOV-1 | Naive vs governed vs interruptive burden, watch vs page separation, lead time | analytical | MIMIC-IV 3.1 credentialed | test | PE-1/PE-2 + secondary endpoints | pending | pending | pending | Blocked (splits + labels) |
| ROB-1 | Pre-specified robustness: urine grace windows, detection windows, partial-score policy, pressor unknown-dose handling, FiO2/PaO2 preference, SpO2 fallback, ESRD/comfort/OR variants, split stability, bootstrap seed 42 | analytical | MIMIC-IV 3.1 credentialed | test (pre-specified only) | effect direction + CIs | pending | pending | pending | Blocked; scaffolding in `eval/mimic_study/bootstrap.py` (seed 42, 1000 replicates) |
| EICU-1 | eICU completeness/portability analysis | analytical-audit | eICU-CRD demo | demo smoke (50 stays) | component missing rates | `python -m eval.mimic_study.eicu_audit` | `data/audit/eicu_portability_audit.json` | `6741cef4…59959e` | audit-only, not frozen; explicitly not clinical validation |
| EICU-2 | Legacy "n=8000" eICU completeness numbers (implementation-backlog Milestone 11) | analytical | eICU-CRD full | protocol-seeded n=8000 | component missing rates | `measure_eicu_sofa_missingness` | — | — | **UNVERIFIED** — cannot be re-run: credentialed eICU absent (`CURIE_EICU_DIR` unset). Old narrative values must not be reused |
| NON-1 | Clinical SOFA accuracy / superiority to NEWS/qSOFA | prohibited | — | — | — | — | — | — | must not appear |
| NON-2 | Improved outcomes / mortality prediction / treatment benefit | prohibited | — | — | — | — | — | — | must not appear |
| NON-3 | Clinical validation on MIMIC or eICU | prohibited | — | — | — | — | — | — | must not appear; eICU is completeness/portability only |
| NON-4 | FDA/SaMD readiness or production readiness | prohibited | — | — | — | — | — | — | must not appear |
| NON-5 | "External validation from unlabeled dumps or demo data" | prohibited | — | — | — | — | — | — | must not appear |
| NON-6 | MIMIC/eICU as a second confirmation of the Challenge 2019 setB governance claim | prohibited | — | — | — | — | — | — | must not appear; Challenge 2019 is a separate frozen cohort |

## Integration-gate evidence (2026-09-05)

- `codex/review-fixes` HEAD `83e4110` == `origin/main` HEAD: the Phase B review fixes
  exist only as **uncommitted working-tree changes**.
- Phase B blocker B1 (MIMIC `rateuom`) is **not wired** into
  `ingestion/adapters/mimic/extract.py`; the typed conversion policy +
  audit exist in `ingestion/adapters/mimic/vasopressors.py` (tests pass), and the
  read-only audit shows 519,642/519,878 mapped pressor rows are `mcg/kg/min`, 2 are
  `mg/kg/min` (would be silently 1000× wrong under the current adapter), 234 have
  missing rate/unit.
- Phase C: `eval/mimic_study/indexing.py` (stay-partitioned Parquet index) is
  in-flight/uncommitted; no frozen label run or comparator run exists; no
  full-cohort indexed replay command is wired to the Makefile yet.

## Regeneration commands

```bash
python -m eval.mimic_study.cohort_flow --json-out data/audit/mimic_cohort_flow.json
python -m eval.mimic_study.completeness_audit --json-out data/audit/mimic_completeness_audit.json
python -m eval.mimic_study.eicu_audit --json-out data/audit/eicu_portability_audit.json
python -m pytest -q                                  # 394 passed (2026-09-05)
python -m eval.parity.gate                           # PARITY_OK=true fixtures=34 mismatches=0
make flink-test                                      # blocked: Docker daemon not running (OrbStack)
```

Artifact hashes are SHA-256 of the JSON files in `data/audit/`. All audit outputs
carry `"status": "AUDIT_ONLY_NOT_FROZEN"`.
