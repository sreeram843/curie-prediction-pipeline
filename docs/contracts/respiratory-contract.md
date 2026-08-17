# Respiratory deterioration contract v0.1

Prototype only — not clinically validated.

**Bundle:** `resp-deterioration` **v0.1.0** · `score.type` = `resp_hypoxemia` ·
`indicator` = `respiratory-deterioration`.

Deterministic hypoxemic / ventilatory deterioration for CURIE-013. Projects onto
the shared clinical-signal contract; participates in shared governance and
episode arbitration. **Not** a separate Flink job or dashboard renderer.

## Inputs

| Field | Notes |
|---|---|
| `pao2_fio2` / `spo2_fio2` | Prefer PaO2/FiO2 when present |
| `pao2_mmhg` + `fio2_fraction` | Ratio derived |
| `spo2_percent` + `fio2_fraction` | Ratio derived; SpO2 alone never assumes ambient FiO2 unless `room_air=true` |
| `respiratory_rate` | Tachypnea staging |
| `oxygen_device` | `none` / `nasal_cannula` / `face_mask` / `high_flow` / `non_invasive` / `invasive` |
| `mechanically_ventilated` | Forces support stage 3 |
| `abg_ph` / `paco2_mmhg` | Optional blood-gas context |

## Staging → score

Final **stage = max(oxygenation, rate, support, blood_gas)**; score = `{0:0, 1:2, 2:4, 3:6}`.

### Oxygenation (ratio)

| Ratio | Stage |
|---|---|
| ≥ 400 | 0 |
| < 400 | 1 |
| < 300 | 2 |
| < 200 | 2 (3 if ventilated) |
| < 100 | 3 |

### Respiratory rate

| RR | Stage |
|---|---|
| < 22 | 0 |
| ≥ 22 | 1 |
| ≥ 30 | 2 |
| ≥ 35 | 3 |

### Oxygen support

| Device | Stage |
|---|---|
| none | 0 |
| nasal_cannula / face_mask | 1 |
| high_flow / non_invasive | 2 |
| invasive / mechanically ventilated | 3 |

### Blood gas (optional)

| Finding | Stage |
|---|---|
| pH < 7.30 or PaCO2 > 50 | ≥ 1 |
| pH < 7.25 or PaCO2 > 60 | ≥ 2 |
| pH < 7.20 | ≥ 3 |

## Acuity

Same bands as AKI prototype: watch ≥ 2, urgent ≥ 4, critical ≥ 6.

## Code

- Scorer: `eval/respiratory/scoring.py`
- Adapter: `eval.signals.contract.signal_from_respiratory`
- Plugin: `resp-deterioration` / `resp_hypoxemia`
- Fixtures: `eval/fixtures/golden/resp_cases.v0.1.json`
