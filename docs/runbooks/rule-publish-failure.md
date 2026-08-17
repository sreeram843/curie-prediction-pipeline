# Runbook: rule publish failure

## Symptom

`make rules` (or `./scripts/publish_rules.sh`) exits non-zero with no publish.

## Diagnose

The script refuses to publish when **either** of two gates fail. Run each directly:

```bash
python -m eval.parity.gate     # parity gate — must print PARITY_OK=true with fixtures>=1
python -c "from eval.indicators.registry import validate_activation; validate_activation()"
```

- `validate_activation()` fails when an active bundle's `score.type` has no registered `IndicatorPlugin`.
- The parity gate fails when Python golden fixtures drift from recorded values or the Java tests fail.

## Fix

- **Activation invalid:** you added a bundle but missed the plugin registration, or added a plugin but no
  activation entry. Wire all of: bundle file + `activation.json` entry + `IndicatorPlugin` registration +
  Python scorer + Java runtime impl + parity fixtures. See
  [`../contracts/indicator-plugin-sdk.md`](../contracts/indicator-plugin-sdk.md).
- **Parity drift:** a scorer changed without updating `eval/fixtures/golden/` and the matching Java test.
  Reconcile Python and Java, update both fixture sets, then re-run `make parity`.

Do **not** bypass the gate. Publishing a drifted bundle is the failure mode the gate exists to prevent.
