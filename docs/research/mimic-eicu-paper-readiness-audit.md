# MIMIC/eICU paper-readiness audit status (2026-09-05)

Companion to the [plan](../../superpowers/plans/2026-09-05-mimic-eicu-paper-readiness.md)
and the [claims ledger](./mimic-eicu-claims-ledger.md). Everything here is
**audit-only**: the Phase B / Phase C integration gate has passed, but no
frozen study numbers exist and none were created.

## Gate verdict

| Gate | State on 2026-09-05 |
|---|---|
| Phase B correctness branch integrated | **Yes** — merged into review baseline `90e4ded`, including respiration resolution, eICU unknown-dose handling, availability-time replay, and state freshness |
| Phase C infrastructure branch integrated | **Yes** — merged indexed replay and manifest scaffolding; label and comparator runs remain future work |

Consequence: only audit/test scaffolding is reportable. **No final numbers were
frozen.** The existing frozen artifacts (`protocol.v1.json`,
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
   `mg/kg/min`, 234 with missing rate/unit. The merged adapter now applies the
   typed conversion policy and preserves unknown cases explicitly.
4. **Completeness + reconciliation + sharded replay**
   (`data/audit/mimic_completeness_audit.json`, hash in ledger): streaming
   per-component observation rates, first-ICU-day coverage, event-time
   distribution, dose-known vs unknown, timestamp/valuenum parse failures,
   runtime/peak RSS, loader-vs-direct row reconciliation, and a seeded 8,000-stay
   sharded replay for complete/partial SOFA coverage.
5. **eICU** (`data/audit/eicu_sofa_missingness_n8000.json`, sha256
   `e2f303fff11c868b88f0e5f2ea171e0286220f62cc04dc07dc766207d900fe2a`):
   credentialed protocol-seeded n=8000 audit remeasurement; current respiration
   missingness is 59.725% (4,778/8,000). The earlier 53.1% figure is a baseline
   raw-S/F result and is not comparable after the corrected S/F→P/F policy.

## Validation recorded

- Focused post-merge Python checks: **164 passed**; local Java/Flink Maven tests:
  **60 passed**.
- `python -m eval.parity.gate`: **PARITY_OK=true fixtures=34 mismatches=0**.
- `ruff check .`: one pre-existing exception in
  `eval/manuscript/make_figures.py`; changed workstream paths are clean.
- `make flink-test` (Maven via Docker): **blocked** — Docker daemon not running
  (OrbStack); external-service failure, recorded not hidden.
- `git diff --check`: clean. `make paper-tables`: rebuilds deterministically.
