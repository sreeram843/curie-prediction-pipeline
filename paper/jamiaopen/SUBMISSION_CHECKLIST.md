# JAMIA Open submission checklist

Venue: https://academic.oup.com/jamiaopen

## Package in this folder

| File | Purpose |
|------|---------|
| `../main.tex` | Article-class manuscript (tables from frozen JSON) |
| `cover_letter.tex` | Cover letter |
| `SUBMISSION_CHECKLIST.md` | This file |

Compile from `paper/`:

```bash
cd paper
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Cover letter:

```bash
cd paper/jamiaopen
pdflatex cover_letter.tex
```

## Before submit

- [ ] Research and Applications article type
- [ ] Structured abstract within venue word limit
- [ ] Lay summary if required by the portal
- [ ] Tables/figures regenerated from `make paper-tables` (no hand-copied metrics)
- [ ] Claim boundary: retrospective Challenge 2019 evaluation, not clinical validation
- [ ] Related papers / prior review history disclosed (or “None”)
- [ ] Data availability: Challenge 2019 v1.0.0 CC-BY 4.0; frozen sidecars in-repo
- [ ] Competing interests
- [ ] Optional first pass: ML4H short/findings; hold IEEE JBHI until MIMIC-IV + eICU Stage B

Condensed venue draft (markdown): `docs/research/jamia-open-submission.md`.
