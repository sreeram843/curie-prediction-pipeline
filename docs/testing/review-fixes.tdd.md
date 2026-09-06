# Review-fixes verification evidence

Source plan: [`docs/superpowers/plans/2026-09-05-streaming-review-fixes.md`](../superpowers/plans/2026-09-05-streaming-review-fixes.md)

## Scope

- Full credentialed eICU paths require `CURIE_EICU_DIR`; shared cohort helpers no longer make the
  ingestion layer import evaluation code.
- Unknown vasopressor dose remains `None`; pressor presence and dose are represented separately.
- Respiration resolution is centralized: PaO2 is preferred, SpO2 is the fallback, FiO2 is required,
  and the 24-hour pairing window is enforced.
- Urine-output SOFA input is unavailable until a complete 24-hour stay window exists.
- Streaming evaluation uses availability time while feature values retain clinical occurrence time;
  late corrections are passive only when explicitly enabled.
- FHIR blood-pressure panels derive MAP only from paired SBP/DBP components; eICU invasive ventilation
  is emitted only from explicit ventilation charting.
- CURIE-042 is restored. CURIE-045 is explicitly in progress; its n=500 result is labeled preview.

## Test evidence

| Guarantee | Test target | Result |
| --- | --- | --- |
| Full eICU path is explicit and validates required files | `eval/mimic_study/test_completeness_check.py` | PASS |
| Unknown dose stays null and uses the configured fallback pressor points | `eval/mimic_harness/test_harness.py`, `ingestion/adapters/eicu/test_eicu.py` | PASS |
| Urine is missing before 24 hours and eligible at the boundary | `eval/mimic_harness/test_harness.py` | PASS |
| Respiration preference, fallback, stale-data, and availability rules are deterministic | `ingestion/adapters/test_respiration.py`, harness and adapter tests | PASS |
| Availability-clock buffering and late correction behavior are explicit | `eval/sofa/test_stream_scorer.py`, `eval/replay_harness/test_governance.py`, Java operator/governance tests | PASS |
| Sepsis-3 baseline policy and provenance are explicit | `eval/sepsis3/test_phenotype.py`, `eval/signals/test_contract.py` | PASS |
| FHIR BP-panel MAP and eICU ventilation mappings are evidence-backed | `streaming/flink-jobs/sofa/.../FhirSofaMapperTest.java`, `ingestion/adapters/eicu/test_eicu.py` | PASS |
| Python/fixture parity is preserved | `.venv/bin/python -m eval.parity.gate` | `PARITY_OK=true fixtures=34 mismatches=0` |
| Repository Python tests | `.venv/bin/pytest -q` | `361 passed` |
| Local Java/Flink Maven tests | `mvn -B -q test` in `streaming/flink-jobs` | PASS |

## Known gap

`make flink-test` could not invoke its Docker-based Maven wrapper because the Docker daemon was
unavailable. The equivalent local Maven test command passed. Repository-wide Ruff still reports
unrelated existing findings in `eval/manuscript/make_figures.py`; changed files pass Ruff.

The credentialed eICU n=8000 respiration remeasurement was run with the merged review baseline:
4,778/8,000 stays (59.725%) were missing respiration; artifact sha256 is
`e2f303fff11c868b88f0e5f2ea171e0286220f62cc04dc07dc766207d900fe2a`. The historical 53.1%
figure reproduces only with the pre-correction scorer; the current Rice S/F→P/F policy fails
closed above SpO₂ 97%. CURIE-045 remains open because its “drops further” acceptance condition
is not met; the extraction implementation and replay measurement are complete, but the result
requires a documented policy decision before changing the acceptance target.
