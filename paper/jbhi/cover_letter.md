September 29, 2026

Editor-in-Chief  
IEEE Journal of Biomedical and Health Informatics

Dear Editor-in-Chief,

Please consider the regular paper “Missingness-Aware SOFA Reconstruction Across Two ICU
Databases With a Locked Alert-Governance Evaluation in MIMIC-IV” for publication in the IEEE
Journal of Biomedical and Health Informatics.

The manuscript addresses a biomedical-informatics problem that sits between EHR data engineering
and clinical decision-support delivery: a deterministic score can silently conflate an unobserved
component with a normal component, and an alert evaluation can silently conflate score events with
clinician interruptions. We present an availability-time SOFA reconstruction contract with explicit
partial and insufficient-data states, evidence provenance, versioned rules, and a separately
versioned governance layer. We audit extraction completeness in MIMIC-IV 3.1 and eICU-CRD 2.0 and
evaluate a development/calibration-selected policy once on a locked 14,407-stay MIMIC-IV test set.
The principal result is deliberately endpoint-specific: governed loose-window sensitivity was
98.49%, while interruptive sensitivity was 71.36%, and governed interruptive emissions were 7.67%
of the naive interruptive baseline. Clearly labeled post hoc analyses show that requiring at least
2 h of lead time reduces governed sensitivity to 54.43% and that, against an independent
discharge-code sepsis label, stay-level alerting is weakly specific. The work characterizes a
retrospective research prototype; it does not claim clinical validation, improved outcomes,
deployment readiness, or regulatory status.

Related-work disclosure: a separate manuscript, “Governing Interruptions After Deterministic
Deterioration Scoring: A Retrospective Evaluation on PhysioNet Challenge 2019,” is under review at
the International Journal of Medical Informatics (manuscript IJMEDI-S-26-06829). It evaluates alert
governance on the PhysioNet Challenge 2019 benchmark. The present submission uses neither that
cohort nor its holdout results, tables, or figures. Its primary contribution is the
missingness-aware EHR reconstruction and provenance boundary together with a locked MIMIC-IV
evaluation; eICU-CRD is used only for extraction completeness. We disclose the related manuscript so
the editorial office can assess the scientific separation directly, and we will provide it on
request. The present manuscript is not concurrently under consideration in substantively
equivalent form elsewhere.

The manuscript uses deidentified, credentialed-access PhysioNet data. Patient-level data are not
redistributed. Versioned aggregate evidence, content hashes, rule bundles, tests, and reproduction
commands are available in the public repository cited in the manuscript.

This work is original, the sole author has approved the manuscript, and the author declares no
competing interests and no funding. The study is a secondary analysis of deidentified data obtained
under PhysioNet data-use agreements, with no new data collection or participant contact; it did
not require independent ethics review, and no new consent was sought because the source databases
were created under approvals that waived individual consent. Artificial intelligence
assistance (OpenAI Codex, the Cursor agent, and Claude Code) is disclosed in the manuscript
acknowledgment in accordance with IEEE policy. We intend to publish under the traditional
(non-open-access) option.

Thank you for your consideration.

Sincerely,

Satya Venkata Ranga Janaki Sriram Mentey  
Independent Researcher  
Austin, Texas, USA  
srirammentey@ieee.org  
ORCID: 0009-0007-2681-006X
