# Challenge 2019 evaluation reproducibility

Paper numbers in `main.tex` / `paper/tables/` come from committed frozen
sidecars under `eval/challenge2019/frozen/`. Do not hand-copy metrics into the
manuscript.

## Cited holdout

- **Dataset:** PhysioNet/Computing in Cardiology Challenge 2019 v1.0.0 (CC-BY 4.0)
- **Selection:** `training_setA` (20,336 stays) — tune and freeze
- **Holdout:** `training_setB` (20,000 stays) — quote once; never retune
- **Primary window:** `window_m12_p6` (any emission in `[label_start−12 h, label_start+6 h]`)
- **Winner:** `eval/challenge2019/frozen/p1_setA_winner.json` (`grid_p0_r90_b0`)
- **Bundle:** `eval/challenge2019/frozen/sepsis-sofa.challenge2019-p1.v1.json`

## One command (tables + manifest)

```bash
pip install -e ".[dev]"
make paper-tables
make manuscript
make manuscript-phi
```

SetB analyses (comparators, ablation, miss table, bootstrap CIs). This is a
regression reproduction, not permission to retune:

```bash
make challenge-2019-paper-analyses
```

Holdout replay of the frozen winner:

```bash
GOV_CONFIG=eval/challenge2019/frozen/p1_setA_winner.json \
SET=training_setB LIMIT=0 make challenge-2019
```

## Freeze checklist (before citing numbers)

1. `git rev-parse HEAD` → record commit; prefer a clean tree
2. Keep frozen sidecars versioned; never replace a frozen file in place
3. Record: detection window `window_m12_p6`, bootstrap seed 42 / 1,000 replicates
4. Do **not** hand-edit CSVs under `paper/tables/` — regenerate via
   `python -m eval.manuscript.generate_paper_tables`
5. Do **not** quote MIMIC demo, eICU demo, FHIR demo, SYN-ICU, or Synthea as
   detection or burden results

## Pinned result artifacts

| Sidecar | Role |
|---|---|
| `p1_setA_winner.json` | Frozen setA operating point |
| `timing_primary.v1.json` | Primary timing policy |
| `holdout_primary_window_m12_p6.v1.json` | SetB point estimates |
| `holdout_primary_window_m12_p6.v2.json` | Stay-level bootstrap 95% CIs |
| `comparators_setB_window_m12_p6.v1.json` | Hourly SIRS / NEWS2 / qSOFA |
| `ablation_setB_window_m12_p6.v1.json` | Drop-one governance on setB |
| `miss_analysis.v2.json` | Aggregated governed FNs (no stay IDs) |
| `pareto_named_profiles.v1.json` | Named profiles + winner on setA |
| `robustness_summary.v1.json` | Secondary timing definitions |
| `sepsis-sofa.challenge2019-p1.v1.json` | Resolved study rule bundle |

The reproducibility manifest is `eval/manuscript/frozen/reproducibility_manifest.v2.json`.

Patient-level Challenge files remain under gitignored `data/archive/`.
