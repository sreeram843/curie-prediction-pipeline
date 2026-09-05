# Review-fixes verification evidence

Source plan: [`docs/superpowers/plans/2026-09-05-review-fixes.md`](../superpowers/plans/2026-09-05-review-fixes.md)

## Scope

- Full credentialed eICU paths require `CURIE_EICU_DIR`; shared cohort helpers no longer make the
  ingestion layer import evaluation code.
- Unknown vasopressor dose remains `None`; pressor presence and dose are represented separately.
- Respiration resolution is centralized: PaO2 is preferred, SpO2 is the fallback, FiO2 is required,
  and the 24-hour pairing window is enforced.
- Urine-output SOFA input is unavailable until a complete 24-hour stay window exists.
- CURIE-042 is restored. CURIE-045 is explicitly in progress; its n=500 result is labeled preview.

## Test evidence

| Guarantee | Test target | Result |
| --- | --- | --- |
| Full eICU path is explicit and validates required files | `eval/mimic_study/test_completeness_check.py` | PASS |
| Unknown dose stays null and uses the configured fallback pressor points | `eval/mimic_harness/test_harness.py`, `ingestion/adapters/eicu/test_eicu.py` | PASS |
| Urine is missing before 24 hours and eligible at the boundary | `eval/mimic_harness/test_harness.py` | PASS |
| Respiration preference, fallback, stale-data, and availability rules are deterministic | `ingestion/adapters/test_respiration.py`, harness and adapter tests | PASS |
| Python/fixture parity is preserved | `.venv/bin/python -m eval.parity.gate` | `PARITY_OK=true fixtures=34 mismatches=0` |
| Repository Python tests | `.venv/bin/pytest -q` | `361 passed` |
| Local Java/Flink Maven tests | `mvn -B -q test` in `streaming/flink-jobs` | PASS |

## Known gap

`make flink-test` could not invoke its Docker-based Maven wrapper because the Docker daemon was
unavailable. The equivalent local Maven test command passed. Repository-wide Ruff still reports
unrelated existing findings in `eval/manuscript/make_figures.py`; changed files pass Ruff.

The credentialed eICU n=8000 respiration remeasurement was not run in this worktree. CURIE-045
therefore remains open, and the existing n=500 extraction result is retained only as a preview.
