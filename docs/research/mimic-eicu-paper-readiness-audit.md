# MIMIC/eICU paper-readiness audit status (2026-09-05)

Companion to the [plan](../../superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md)
and the [claims ledger](./mimic-eicu-claims-ledger.md). Everything here is
**audit-only**: the Phase B / Phase C integration gate has not passed, so no
frozen study numbers exist and none were created.

## Gate verdict

| Gate | State on 2026-09-05 |
|---|---|
| Phase B correctness branch integrated | **No** — `codex/review-fixes` HEAD (`83e4110`) == `origin/main`; the review fixes (respiration resolver, eICU unknown-dose, harness urine/24h, etc.) exist only as uncommitted working-tree changes; B1 (`rateuom`) is audited + typed + tested but **not wired** into the scoring adapter |
| Phase C infrastructure branch integrated | **No** — `eval/mimic_study/indexing.py` (Parquet index) is in-flight/uncommitted; no label-run or comparator-run exists; no Makefile-wired full-cohort replay |

Consequence: per the plan, only audit/test scaffolding was produced. **No final
numbers were frozen.** The existing frozen artifacts (`protocol.v1.json`,
`operating_point.v1.json`, `study_manifest.v1.json` — all demo-schema) were not
touched.

## Audit results (regenerable, unfrozen)

Artifacts under gitignored `data/audit/`; all carry `"status": "AUDIT_ONLY_NOT_FROZEN"`.

1. **Cohort flow** (`data/audit/mimic_cohort_flow.json`, sha256 `07e0f207…9aede`):
   94,458 icustays → 84,855 final cohort stays (adult ≥18, first ICU stay per
   admission, LOS ≥ 4h, valid intime/outtime) with per-step denominators; ESRD
   5,567 / comfort-care 13,042 / OR-transfer 71 stays counted under declared
   policies.
2. **Split finding**: MIMIC-IV v3.1 de-identifies dates with a per-subject random
   shift into deidentified years 2100–2200 ("distinct patients are not temporally
   comparable" per the official v3.1 documentation). The frozen protocol v1
   calendar splits (2008–2019 by ICU intime) are **inapplicable**; only
   `anchor_year_group` (3-year buckets: 2008-10 … 2020-22) preserves approximate
   order. Split assignment is **suspended pending a protocol amendment**.
3. **Pressor unit audit** (`data/audit/mimic_pressor_unit_audit.json`, sha256
   `fcf703d5…113`): 519,878 mapped pressor rows; 519,642 `mcg/kg/min`, 2
   `mg/kg/min` (silently misinterpreted by the current unwired adapter), 234 with
   missing rate/unit.
4. **Completeness + reconciliation + sharded replay**
   (`data/audit/mimic_completeness_audit.json`, hash in ledger): streaming
   per-component observation rates, first-ICU-day coverage, event-time
   distribution, dose-known vs unknown, timestamp/valuenum parse failures,
   runtime/peak RSS, loader-vs-direct row reconciliation, and a seeded 8,000-stay
   sharded replay for complete/partial SOFA coverage.
5. **eICU** (`data/audit/eicu_portability_audit.json`, sha256 `6741cef4…59959e`):
   demo smoke only (50 stays; respiration missing in 38/50). Full-cohort eICU and
   the legacy "n=8000" re-run are **blocked** (no credentialed eICU data); old
   narrative numbers are marked unverified in the ledger.

## Validation recorded

- `pytest -q`: **394 passed** (incl. integration with local demo data).
- `python -m eval.parity.gate`: **PARITY_OK=true fixtures=34 mismatches=0**.
- `ruff check .`: clean for all files in this workstream; two pre-existing /
  in-flight exceptions: `eval/manuscript/make_figures.py` (unmodified since main)
  and the concurrently-authored `eval/mimic_study/indexing.py`.
- `make flink-test` (Maven via Docker): **blocked** — Docker daemon not running
  (OrbStack); external-service failure, recorded not hidden.
- `git diff --check`: clean. `make paper-tables`: rebuilds deterministically.
