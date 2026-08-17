# Runbook: parity drift

## Symptom

`make parity` (or CI `parity` job) fails, or reports a nonzero mismatch count.

## Diagnose

```bash
python -m eval.parity.gate          # Python side: fixture count + mismatches
make flink-test                     # Java side: Maven surefire tests
```

The gate compares the Python reference scorer against `eval/fixtures/golden/` and cross-checks the Java
runtime. A mismatch means one side changed without the other.

## Fix

1. Identify the drifting scorer (SOFA, AKI timeline, respiratory, hemodynamic, or governance).
2. Reconcile Python (`eval/*/scoring.py`) and Java (`streaming/flink-jobs/sofa/...`) behavior.
3. Update `eval/fixtures/golden/` **and** the matching Java test for any intentional change.
4. Re-run `make parity` until `PARITY_OK=true` and `fixtures>=1`.

## Guardrail

Golden fixtures change only alongside a scorer change; never edit them in place to "make a test pass" —
that silently rewrites the contract. See [`../adr/0004-dual-runtime-parity.md`](../adr/0004-dual-runtime-parity.md).
