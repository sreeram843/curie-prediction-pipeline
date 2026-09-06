# Stage B code-path verification

This note records repository-side verification for the MIMIC-IV/eICU Stage B
workflow. It is not a clinical validation report and contains no PhysioNet
patient data or Stage B performance estimates.

## Implemented path

- `eval/mimic_study/frozen/protocol.v2.json` uses MIMIC `anchor_year_group`
  buckets for development, calibration, and locked test roles.
- `scripts/materialize_mimic_labels.py` consumes operator-produced SQL exports
  plus a pinned `mimic-code` JSON pin and writes a content-hashed label sidecar.
- Indexed replay accepts an explicit protocol and validated label artifact;
  labels are attached only as replay metadata and never become features.
- Indexed patient metadata retains `anchor_year_group` for protocol assignment.
- `run-rows` executes the same locked selection/evaluation orchestration over
  canonical rows from either data source. v2 output paths are versioned.
- `eval.mimic_study.index_replay export-rows` creates those canonical rows from
  a validated indexed replay, so the v2 study path does not require a manual
  data reshaping step.
- Metrics expose fixed lead-time ranking/calibration primitives, false episode
  rate, interruptive precision, and decision-curve net benefit.

## Required external inputs

The following remain operator/data-custodian steps: credentialed MIMIC-IV 3.1
access, pinned `mimic-code` checkout, execution of the vetted SQL concepts,
canonical stay-row generation, and the eICU extract. No labels, operating
point, or test metrics are frozen by this code-only change.

## Verification

Verification completed on 2026-09-06:

- `pytest -q`: 543 passed (5 existing dependency deprecation warnings).
- `python -m eval.parity.gate`: `PARITY_OK=true`, 43 fixtures, 0 mismatches.
- `make flink-test`: passed through Maven/Docker.
- `ruff check .`: passed.
- `git diff --check`: passed.
- The v2 CLI smoke test against the synthetic demo fixture reported
  `selection_used_test: false`.

The repository-wide Ruff command still reports 11 pre-existing findings in
`eval/manuscript/make_figures.py`; that unrelated file was not changed here.
