# Challenge 2019 alert-governance paper

This directory holds the methods paper and generated artifacts, in the same
layout as CurieFHIR `paper/`.

See **[REPRODUCIBILITY.md](REPRODUCIBILITY.md)** for the freeze checklist and
commands. Working markdown is [DRAFT.md](DRAFT.md); the compiled article is
[main.tex](main.tex). JAMIA Open submission files live in [jamiaopen/](jamiaopen/).

## Reproduce tables (do not hand-copy numbers)

Every number in the results section should come from `paper/tables/*.csv` or
`paper/tables/*_tabular.tex` — regenerate from frozen sidecars:

```bash
pip install -e ".[dev]"
make paper-tables          # python -m eval.manuscript.generate_paper_tables
make manuscript            # also rebuilds the reproducibility manifest
make manuscript-phi
```

SetB comparators, ablation, miss attribution, and bootstrap CIs (never retune):

```bash
make challenge-2019-paper-analyses
```

Compile the article (needs a TeX install):

```bash
cd paper
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## Notes

- **One results dataset:** PhysioNet Challenge 2019 v1.0.0 (CC-BY 4.0).
- MIMIC-IV demo, eICU demo, FHIR demo, SYN-ICU, and Synthea are adapter
  coverage only — they never contribute sensitivity or burden estimates.
- Do **not** hand-edit CSVs or `*_tabular.tex` under `paper/tables/`.
- Do **not** retune governance on `training_setB`.
- Prototype only: not clinically validated, not FDA-cleared, not for patient care.
