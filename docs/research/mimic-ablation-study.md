# MIMIC ablation and robustness study (CURIE-016)

**Status:** Demo-schema locked study — regenerable via one command  
**Runner:** `make mimic-study` / `python -m eval.mimic_study.study run`  
**Frozen:** [`eval/mimic_study/frozen/operating_point.v1.json`](../../eval/mimic_study/frozen/operating_point.v1.json),
[`eval/mimic_study/frozen/study_manifest.v1.json`](../../eval/mimic_study/frozen/study_manifest.v1.json)
**Protocol:** [`mimic-iv-study-protocol.md`](./mimic-iv-study-protocol.md)

> Synthetic demo-schema only. Not Stage B clinical results. Do not retune on the test split.

## Guarantees (acceptance)

1. **Thresholds / knobs selected only on development + calibration** (OPS-1). Selecting on `test` raises `ProtocolError`.
2. **Locked test holdout evaluated once** for the primary operating point and for each pre-specified ablation.
3. **All tables regenerate** from `make mimic-study` (recorded in the study manifest).

## Ablations

From protocol `ablations.pre_specified`:

| ID | Meaning |
|---|---|
| `threshold_only_naive` | Score tier → alert; no governance |
| `full_governance` | Frozen operating-point knobs |
| `drop_persistence` | persistence = 0 |
| `drop_crossings` | min_crossings = 1 |
| `drop_baseline` | baseline off |
| `drop_refractory` | refractory = 0 |
| `drop_context_suppression` | empty suppression flags |
| `drop_page_gate` | page gate off |
| `drop_episode_arbitration` | each alert counted separately |
| `drop_late_event_buffer` | accept out-of-order event times |

## Metrics reported

Sensitivity (naive / governed / interruptive) under `window_m12_p6`, interruptive reduction ratio, alerts and episodes per 100 patient-days, NNA, in-window lead time, false episodes on label-negative stays, partial-completeness counts, PE-1 / PE-2 flags.

## Commands

```bash
make mimic-study
python -m eval.mimic_study.study guard-test   # must print PROTOCOL_VIOLATION
python -m eval.mimic_study.study show-manifest
```
