# Cover letter — JAMIA Open

> Fill the bracketed fields before submission. JAMIA Open requires the cover letter to disclose any
> related papers and any prior review history for this work.

[Date]

To the Editors, *JAMIA Open*

Dear Editors,

We submit our manuscript, **"Governing interruptions after deterministic deterioration scoring: a
retrospective alert-policy evaluation on PhysioNet Challenge 2019,"** for consideration as a Research
and Applications article.

Most retrospective deterioration studies treat a positive score as the alert. We instead evaluate
the *interruption decision* as a separable, versioned policy that runs after a deterministic score
and before a page is emitted. Using the public PhysioNet/Computing in Cardiology Challenge 2019
dataset, we tuned a dual-lane governance policy on setA, froze it with a content hash, and evaluated
setB once. The governed path matched threshold-only partial-SOFA detection (79.5%, 95% CI 77.0–81.8)
while the interruptive lane emitted 13.2% as many alerts. Against hourly SIRS, incomplete NEWS2, and
partial qSOFA on the same window, and through drop-one mechanism ablations, we localize the burden
reduction to two specific mechanisms — a 90-minute refractory interval and a page gate — rather than
to governance as a whole. We believe this mechanism-level, fully reproducible treatment of alert
governance fits JAMIA Open's readership in clinical decision support and alert fatigue.

We are explicit about scope. This is a retrospective offline evaluation against a proxy label
(`SepsisLabel`) using a partial SOFA reconstruction on a single public challenge; it is not clinical
validation and makes no claim of diagnosis, outcome improvement, external validity, or regulatory
readiness. All operating points, timing policies, rule bundles, bootstrap and ablation sidecars, and
content hashes are committed, and every table and figure regenerates from a documented command.

We confirm that: this manuscript is original, is not under consideration elsewhere, and has not been
previously published; all authors have approved the submission; and the work involves only publicly
available, de-identified challenge data (no new human-subjects data collection).

**Related papers and prior review history:** [State any preprint — e.g. an ML4H short-form version —
and any prior submission or peer review of this work, or write "None."]

**Data and code availability:** Challenge 2019 v1.0.0 is publicly available from PhysioNet under
CC-BY 4.0; derived analysis artifacts and reproducibility commands are described in the manuscript's
Data availability statement.

We have no competing interests to declare [or state as applicable]. We suggest, but do not require,
reviewers with expertise in clinical decision support, alarm/alert fatigue, and sepsis early-warning
evaluation.

Thank you for your consideration.

Sincerely,

[Corresponding author name], on behalf of all authors
[Affiliation]
[Email] · [ORCID]
