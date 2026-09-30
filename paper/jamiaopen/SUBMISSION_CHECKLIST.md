# JAMIA Open submission checklist

Article type: Research and Applications

## Ready in this package

- [x] Double-spaced main manuscript with structured abstract and lay summary
- [x] Four main tables and three main figures
- [x] Separate supplementary PDF with full 23-candidate selection grid
- [x] Separate Figure 1 PDF and alt text for all three figures
- [x] Frozen setB denominators, patient-time, PPV, lead-time distribution, and utility
- [x] SetA estimands distinguished: 88.4% legacy grace-6 selection vs 87.6% primary window
- [x] Label-incorporation bias and incomplete-comparator caveats stated
- [x] Author contributions, funding, conflicts, ethics, data availability, and AI disclosure
- [x] Cover letter

## Author actions required before upload

- [x] Add corresponding-author telephone number to title page and cover letter
- [x] Add highest academic degree after the author name if required by the portal
- [x] Confirm the independent-researcher affiliation and postal address
- [x] Confirm that the GitHub repository is public at submission time
- [x] Confirm ethics wording against the author's applicable institutional policy
- [x] Confirm whether any generative-AI use beyond the disclosed Codex assistance occurred
- [ ] Enter all portal metadata and select the correct article type
- [ ] Upload figures separately and paste the supplied alt text
- [ ] Run the final frozen-artifact/hash verification immediately before submission

See `submission/AUTHOR_TODO.md` for the recorded confirmations and remaining portal steps.

## Files

Fresh ScholarOne upload package (preferred):

| File | Purpose |
|---|---|
| `submission/01_cover_letter.pdf` | Cover letter |
| `submission/02_manuscript_main.pdf` | Main manuscript |
| `submission/03_supplementary_material.pdf` | Supplementary methods and tables |
| `submission/figures/Figure1_system_boundary.pdf` | Standalone Figure 1 |
| `submission/figures/Figure2_detection_burden.pdf` | Standalone Figure 2 |
| `submission/figures/Figure3_timing_robustness.pdf` | Standalone Figure 3 |
| `submission/portal_metadata/` | Title, abstract, lay summary, keywords, alt text |
| `submission/AUTHOR_TODO.md` | Author confirmations before submit |
| `submission/README.md` | Portal upload map |

Source / build copies:

| File | Purpose |
|---|---|
| `../main.pdf` | Main manuscript source build |
| `supplement.pdf` | Supplementary methods and tables |
| `figure1-system-boundary.pdf` | Standalone Figure 1 |
| `../figures/figure3_detection_burden.pdf` | Standalone Figure 2 |
| `../figures/figure4_timing_robustness.pdf` | Standalone Figure 3 |
| `figure-alt-text.md` | Accessible descriptions for Figures 1--3 |
| `cover_letter.pdf` | Cover letter |

Build from `paper/` with `make paper-tables`, then compile the manuscript. Build
the supplement and cover letter from `paper/jamiaopen/` so their relative table
paths resolve. Refresh the upload folder with:

```bash
bash jamiaopen/assemble_submission.sh
```
