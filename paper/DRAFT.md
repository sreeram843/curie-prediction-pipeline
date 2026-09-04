# Working markdown draft

Compiled paper: [`main.tex`](main.tex). Tables in [`tables/`](tables/) are generated from frozen Challenge 2019 JSON (`make paper-tables`) — do not hand-copy metrics. Reproducibility: [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

---

# Governing Interruptions After Deterministic Deterioration Scoring:
# A Retrospective Evaluation on PhysioNet Challenge 2019

**Manuscript status:** methods-paper draft; not submitted  
**Primary venue:** [JAMIA Open](https://academic.oup.com/jamiaopen) (rolling; alert fatigue / CDS)  
**Optional first pass:** ML4H symposium (short / findings) for review feedback  
**Later:** Computing in Cardiology 2027 (CinC 2026 already ran)  
**Hold:** IEEE JBHI until MIMIC-IV + eICU Stage B  
**Results dataset:** PhysioNet/Computing in Cardiology Challenge 2019 only (CC-BY 4.0)  
**Reporting boundary:** retrospective offline evaluation; not clinical validation

**Analysis status (all on `data/archive`; no MIMIC):**

| Item | Status | Artifact |
|---|---|---|
| SIRS / NEWS2 / qSOFA baselines | done | `comparators_setB_window_m12_p6.v1.json` |
| Pareto (named profiles + winner) + bootstrap CIs | done | `pareto_named_profiles.v1.json`, `holdout_primary_window_m12_p6.v2.json` |
| SetB mechanism ablation | done | `ablation_setB_window_m12_p6.v1.json` |
| SetB miss attribution | done | `miss_analysis.v2.json` (not the synthetic v1) |
| License pin | done | CC-BY 4.0 (PhysioNet Challenge 2019 v1.0.0) |
| Rewrite / submit | remaining | this draft → JAMIA Open (optional ML4H short form first) |

Reproduce analyses: `make challenge-2019-paper-analyses`. Tables: `make paper-tables`. Supplementary reproducibility: `make manuscript`.

## Abstract

**Background:** Clinical deterioration scores and clinician interruptions are different design
objects. A threshold can identify a concerning state while still producing repeated or poorly timed
interruptions. Alert governance can apply trajectory, crossing, refractory, and page-eligibility
rules after deterministic scoring and before an interruptive alert is emitted.

**Objective:** To compare a frozen dual-lane governance policy on partial SOFA with
threshold-only partial SOFA and with hourly SIRS, NEWS2, and partial qSOFA, and to
ablate governance mechanisms on a locked Challenge 2019 holdout.

**Methods:** We replayed hourly Challenge 2019 records through a deterministic partial-SOFA scorer
and compared threshold-only SOFA emissions, governed emissions (watch plus interruptive), and
interruptive emissions. Separate hourly SIRS (≥2), NEWS2 (≥5; consciousness omitted), and
partial qSOFA (≥2; GCS omitted) comparators used the same detection window and had no
governance. We tuned governance on `training_setA` (20,336 stays), froze the selected rule
bundle and timing policy, and evaluated `training_setB` (20,000 stays) once. The primary detection
window was any emission in `[label_start−12 h, label_start+6 h]`. Detection used any governed
emission; burden used interruptive emissions. We report stay-level bootstrap 95% CIs (seed 42)
on the primary window and drop-one governance ablations on setB without reselection. The Challenge
label begins approximately six hours before its clinical-onset definition. Files are licensed
CC-BY 4.0.

**Results:** On this Challenge holdout, incomplete NEWS2 (≥5) detected 76.0% of label-positive
stays at 141,629 hourly emissions (NNA 163.2); SIRS (≥2) detected 78.5% at 191,294 emissions
(NNA 213.3); partial qSOFA (≥2) detected 24.9% at 22,068 emissions. Frozen governed partial SOFA
matched threshold-only SOFA sensitivity at 79.5% (95% CI 77.0–81.8) while the interruptive lane
emitted 13.2% as many alerts as naive SOFA (41,158 vs 311,797; NNA 106.1, 95% CI 96.2–116.6).
Ablating the 90-minute refractory interval roughly doubled interruptive volume (reduction 0.132 →
0.264). Removing the page gate raised interruptive sensitivity from 34.0% to 44.6% at higher page
volume. Page-persistence and page-crossing drops did not move hourly Challenge metrics. Dual-lane
design kept detection on a watch path. These are proxy-label, partial-score results, not a claim of
superiority to NEWS or qSOFA in practice.

**Conclusions:** In this retrospective public-challenge evaluation, a frozen governance policy
substantially reduced page-eligible emissions on the selection split while the governed path
retained 79.5% detection on the holdout. These findings concern alert-policy behavior against a
proxy label; they do not establish sepsis diagnosis, clinical benefit, external validity, or safety
for patient care.

## 1. Introduction

Electronic clinical decision support can generate many technically correct but operationally weak
interruptions. Repeated exposure can reduce responsiveness, and many interruptive alerts are closed
quickly, suggesting that interruption cost depends on relevance and workflow fit rather than alert
count alone [1,2]. Sepsis-alert trials have also produced mixed clinical results, reinforcing that a
score's discrimination does not by itself determine the value of the alerting workflow [3].

Most retrospective deterioration studies treat a positive model or rule output as the alert. We
instead treat scoring and interruption as separate stages. A deterministic scorer first produces a
complete, auditable signal. A shared governance layer then determines whether the signal should be
suppressed, shown passively, or emitted through an interruptive lane. The governance policy can use
repeated crossings, temporal persistence, baseline-relative change, refractory windows, and a
page gate without changing the underlying clinical score.

We evaluated this separation using the PhysioNet/Computing in Cardiology Challenge 2019, which
provides hourly ICU records and an onset-aligned `SepsisLabel` [4,5]. The study asks one narrow
question: can a frozen governance policy reduce page-eligible emissions relative to threshold-only
partial SOFA while retaining retrospective label detection?

The supported claim is deliberately limited:

> Shared governance reduces interruptive emissions versus threshold-only partial SOFA while
> retaining retrospective Challenge `SepsisLabel` detection under a frozen setA-to-setB
> evaluation.

We do not evaluate diagnosis, treatment, mortality, clinician adoption, MIMIC-IV performance,
prospective deployment, or regulatory readiness.

## 2. System

### 2.1 Separation of scoring, governance, and narrative

The Curie prototype projects clinical events onto a canonical envelope, transports them through
Kafka, and applies versioned deterministic rules in Apache Flink. The scoring output includes the
score, severity, evidence identifiers, missing components, rule version, and rule-content hash.
Shared governance operates on this deterministic output and assigns passive or interruptive
routing. An optional language-model component may generate a post-alert narrative, but it cannot
create, suppress, escalate, or change an alert.

**Figure 1. System boundary used in the retrospective replay.**

```mermaid
flowchart LR
    A["Hourly clinical events"] --> B["Kafka-compatible event envelope"]
    B --> C["Deterministic partial SOFA"]
    R["Versioned rule bundle"] --> C
    C --> G["Shared alert governance"]
    G --> W["Passive watch emission"]
    G --> P["Interruptive emission"]
    P -. "post-alert only" .-> L["Optional LLM narrative"]
```

The retrospective harness executes the scoring and governance semantics directly. It does not
simulate clinician delivery, acknowledgement, or treatment.

### 2.2 Governance policy

The policy family contains five separable mechanisms:

1. **Crossings:** require repeated qualifying score crossings before selected actions.
2. **Persistence:** require a qualifying state to persist for a configured duration.
3. **Baseline delta:** require meaningful change from a recent patient baseline when enabled.
4. **Refractory interval:** suppress repeated emissions for a configured period.
5. **Page gate:** reserve the interruptive lane for stronger trajectories while preserving a
   passive watch lane.

The setA-selected configuration used one crossing and no persistence requirement for the governed
watch path, disabled baseline gating, and used a 90-minute refractory interval. Its interruptive
page gate required two crossings, 30 minutes of page-level persistence, a score increase of at
least one point, and at least two positive components. Thus, the selected policy preserved a
sensitive passive lane while making the interruptive lane more selective.

## 3. Methods

### 3.1 Dataset and study design

We used PhysioNet Challenge 2019 version 1.0.0. The public resource contains two training
partitions: setA with 20,336 stays and setB with 20,000 stays [4]. The current PhysioNet version page
lists the files under the Creative Commons Attribution 4.0 International license. We used setA to select and
freeze the operating point. We treated setB as a locked retrospective holdout and did not tune or
reselect policy parameters on it.

This is not an official Challenge submission or an evaluation against the hidden Challenge test
set. `training_setB` is a holdout within the same public challenge resource, not an external
hospital validation cohort.

### 3.2 Partial SOFA mapping

SOFA was designed to summarize organ dysfunction across respiratory, coagulation, liver,
cardiovascular, central nervous system, and renal components [6]. Challenge records support only a
partial reconstruction. The replay used available oxygenation, mean arterial pressure, platelet,
bilirubin, and creatinine fields with causal forward filling. The dataset does not provide Glasgow
Coma Scale, urine-output windows, vasopressor-dose ladders, or a reliable mechanical-ventilation
flag. We therefore refer to the result as **partial SOFA**, not complete SOFA and not a sepsis
diagnosis.

Missing inputs were not imputed to reassuring values. The scorer recorded missing components and
required at least two scoreable components under the frozen study bundle.

### 3.3 Comparators and output lanes

At each hourly update, the same partial-SOFA result fed two paths:

- **Threshold-only partial SOFA:** emit whenever the score crossed the configured alert threshold.
- **Governed partial SOFA:** apply the frozen trajectory, crossing, refractory, and page-gate policy.

Governed output was divided into:

- **Any governed emission:** passive watch plus interruptive emissions; used for governed
  detection sensitivity.
- **Interruptive emission:** urgent or critical page-eligible output; used for interruptive
  sensitivity, burden, and interruptive NNA.

“Interruptive emission” is an offline routing decision. It is not an episode-arbitrated page and
was not delivered to a clinician.

Independently of Curie governance, we scored three **hourly threshold-only** bedside comparators
on the same stays and the same primary window:

- **SIRS ≥ 2** using temperature, heart rate, respiratory rate, and white-cell count (all present
  as Challenge columns).
- **NEWS2 ≥ 5** (Royal College of Physicians medium trigger) using respiratory rate, SpO2 scale 1,
  air/oxygen from FiO2, temperature, systolic blood pressure, and heart rate. Consciousness/AVPU
  is absent in Challenge 2019 and was scored 0; we therefore call this an **incomplete NEWS2**.
- **Partial qSOFA ≥ 2** using respiratory rate ≥ 22 and systolic blood pressure ≤ 100. Glasgow Coma
  Scale is absent, so the mentation limb is omitted and a positive score requires both remaining
  limbs.

These comparators have no refractory window or page gate. They are included to place governed
partial SOFA on a detection/burden plane that is not only “governance versus its own threshold.”
They are not a claim of superiority to NEWS or qSOFA in clinical practice.

### 3.4 Operating-point selection and freeze

Governance candidates were evaluated on setA. The selected candidate,
`grid_p0_r90_b0`, was materialized as `p1_setA_winner.json` and bound to the resolved rule bundle
`sepsis-sofa.challenge2019-p1.v1.json`. The bundle content hash was frozen before setB evaluation.
The selected setA point had governed sensitivity of 88.4% and an interruptive-emission ratio of
0.123 relative to threshold-only emissions.

The committed reproducibility package contains the selected point. Named governance profiles
plus that frozen winner are plotted as a sparse frontier (`pareto_named_profiles.v1.json`). That
figure is not a reconstruction of the original 23-candidate setA grid.

### 3.5 Labels and timing

For sepsis-positive Challenge records, `SepsisLabel` becomes positive at approximately six hours
before the Challenge clinical-onset definition [4]. We call the first positive label hour
`label_start`; we do not call it bedside clinical onset.

The primary timing policy was frozen as `window_m12_p6`: a stay was detected if any qualifying
emission occurred in `[label_start−12 h, label_start+6 h]`. Mean lead time was calculated from the
first governed emission within that bounded window to `label_start`. Grace-0 h, grace-6 h,
grace-12 h, early-only, and ±12 h definitions were secondary sensitivity analyses.

### 3.6 Outcomes

The primary holdout metrics were:

- governed sensitivity: proportion of labeled-positive stays with any governed emission in-window;
- interruptive sensitivity: proportion with an interruptive emission in-window;
- interruptive NNA: number of interruptive emissions per interruptive true-positive stay; and
- bounded mean lead time relative to `label_start`.

The selection-split burden metric was the number of interruptive emissions divided by the number of
threshold-only emissions. Primary-window 95% confidence intervals were stay-level percentile
bootstrap intervals (1,000 replicates, seed 42) written to
`holdout_primary_window_m12_p6.v2.json`. Legacy grace-6 h intervals are not transferred to the
primary timing definition.

SetB ablation dropped one frozen mechanism at a time (baseline, persistence including page
persist, crossings including page crossings, refractory interval, page gate) and re-scored setB
without changing the selected winner. Variants whose knobs already matched the winner are reported
as null ablations.

Governed false negatives under the primary window were attributed from replay rows (never
scoreable, never crossed the naive threshold in-window, naive-in-window with no governed emit,
or governed emit only outside the window). The committed miss table contains aggregates only.

### 3.7 Engineering checks and other adapters

Golden fixtures test positive, negative, boundary, and missing-data scorer behavior. Shared fixtures
also check Python reference behavior against the Java/Flink implementation and check governance
decisions across runtimes. A demo-schema ablation harness checks availability-time ordering,
leakage guards, and knob plumbing. These artifacts are appendix methods evidence, not an additional
results cohort.

MIMIC-IV demo, eICU demo, MIMIC-IV FHIR demo, SYN-ICU, and Synthea adapters exercise the same
adapter-to-harness path. We report no sensitivity, burden, calibration, or clinical-effect estimate
from those sources. A full MIMIC-IV protocol is future Stage B work and is not a result in this
paper.

## 4. Results

Numeric tables in the compiled paper are generated from frozen sidecars (`make paper-tables`).
Do not hand-copy metrics into `paper/tables/`.

### 4.1 Selection split

SetA contained 20,336 stays, including 1,790 with a positive `SepsisLabel`. Under the frozen
operating point, threshold-only scoring emitted 529,958 alerts and the interruptive governed lane
emitted 64,928 alerts. The interruptive ratio was 0.123, meaning the selected page-eligible lane
retained 12.3% of threshold-only emission volume on the selection split. Governed sensitivity was
88.4%; interruptive sensitivity was 37.7%.

These are setA selection results. They are not substituted for the setB primary holdout metrics.

### 4.2 Primary setB holdout

Table 1 reports the frozen setB result under `window_m12_p6`. See `paper/tables/holdout.csv`.

The difference between governed and interruptive sensitivity reflects the intended dual-lane
policy: a passive watch can preserve detection without turning every detection into an interruptive
emission. NNA remains high, indicating that emission reduction alone did not produce a clinically
efficient page stream.

### 4.3 Timing-definition robustness

Secondary timing definitions changed absolute sensitivity but produced equal naive and governed
sensitivity for the frozen configuration in each documented analysis. The ordering of the frozen,
dual, accuracy, balanced, and strict profiles was stable across the reported definitions.

See `paper/tables/robustness.csv`. The 81.1% grace-6 h result is a secondary legacy analysis and
must not replace the primary 79.5% result.

### 4.4 Bedside comparators

Table 3 places threshold-only SIRS, incomplete NEWS2, and partial qSOFA on the same primary window
as Curie lanes. Numbers are from `comparators_setB_window_m12_p6.v1.json` (setB, no governance).
See `paper/tables/comparators.csv`. NNA is emissions per in-window true-positive stay for that
lane. NEWS2 omits consciousness; qSOFA omits GCS. Not a clinical superiority claim.

### 4.5 SetB ablation of the frozen winner

Table 4 reports drop-one mechanism evaluations on setB. The operating point is not reselected.
`drop_baseline` is a null ablation (winner already has baseline off). On hourly Challenge spacing,
zeroing page persistence (30 min) or page crossings (2→1) did not change setB metrics; the
90-minute refractory interval and the page-gate routing decision did. See
`paper/tables/ablation.csv`.

### 4.6 Miss attribution

Of 1,142 label-positive setB stays, 234 were governed false negatives under the primary window
(`miss_analysis.v2.json`; aggregates only). See `paper/tables/miss.csv`. No in-window misses were
attributed to refractory on the frozen winner: if naive SOFA fired in-window, a governed emit
existed (possibly outside the window). The synthetic `miss_analysis.v1.json` table is not used as
a result.

## 5. Discussion

### 5.1 Principal finding

This study evaluates the alert policy rather than proposing a new predictive model. On the setB
primary window, incomplete NEWS2 and SIRS approached governed partial-SOFA sensitivity (76.0% and
78.5% vs 79.5%) but as ungoverned hourly streams with NNA 163–213. Partial qSOFA was specific and
quiet (24.9% sensitivity, 22,068 emissions) because the GCS limb is missing. Frozen governance
matched naive SOFA detection at 79.5% (95% CI 77.0–81.8) while the interruptive lane retained 13.2%
of naive SOFA volume (95% CI 12.7–13.7). Ablation shows that the 90-minute refractory interval is
what keeps watch volume below naive SOFA, and that the page gate—not page persist or page
crossings on hourly rows—is what holds interruptive sensitivity at 34.0% rather than 44.6%.

The result supports dual-lane design: retrospective detection can be represented passively while a
more selective policy controls interruption. It does not show that the interruptive lane is already
optimal. An interruptive NNA of 106.1 (95% CI 96.2–116.6) is a substantial residual burden and
should be treated as a design target, not hidden behind the reduction ratio. The comparison to
SIRS/NEWS2/qSOFA is a Challenge-2019 detection/burden plane, not evidence that Curie outperforms
those scores in clinical practice.

### 5.2 Score performance is not alert performance

Threshold-only comparisons often collapse model output, user-interface behavior, and clinician
workflow into one binary alert. The present design makes those layers explicit. Persistence,
crossings, refractory windows, and page gating can be studied as versioned policy parameters while
the clinical score remains unchanged. That separation supports reproducible ablations and clearer
failure attribution, but it does not remove the need for prospective workflow evaluation.

### 5.3 Reproducibility and auditability

The selected operating point, timing policy, resolved rule bundle, and content hashes are committed
as frozen artifacts. Every emitted score carries rule provenance, and shared fixtures exercise the
Python and Java implementations. The language-model layer is outside the alert path and therefore
does not affect any result in this study.

### 5.4 Future work

The next evidence step is not to treat unlabeled demo datasets as external validation. A separate
study should execute a pre-specified MIMIC-IV protocol using availability-time replay, a full or
explicitly partial SOFA reconstruction, Sepsis-3-aligned labels, and subgroup analysis. A later
silent prospective study would be required to measure delivered alert burden, clinician response,
workflow fit, safety, and patient outcomes.

## 6. Limitations

First, Challenge `SepsisLabel` is an onset-aligned proxy derived for a prediction competition. It is
not prospective bedside adjudication, and it begins approximately six hours before the Challenge
clinical-onset definition. Reported lead time is therefore relative to `label_start`, not proof of
six hours of actionable clinical warning.

Second, the score is partial SOFA. Challenge data omit GCS, urine-output windows, vasopressor-dose
ladders, and reliable mechanical-ventilation context. Missing components may alter both score and
policy behavior.

Third, setB is a holdout within one public challenge, not an external clinical cohort. The study does
not estimate transportability, site calibration, distribution shift, subgroup fairness, or
prospective performance.

Fourth, interruptive outputs are emission-level page candidates. They were not episode-arbitrated,
delivered, or reviewed by clinicians. NNA therefore measures retrospective emissions per detected
positive stay, not pages required for a useful clinical action.

Finally, fixture and demo-schema checks prove implementation behavior and reproducibility only.
They do not provide a second clinical cohort and are not used to estimate sensitivity.

## 7. Reproducibility

The manuscript package is rebuilt with:

```bash
make paper-tables
make manuscript
make manuscript-phi
```

The setB replay command is:

```bash
GOV_CONFIG=eval/challenge2019/frozen/p1_setA_winner.json \
SET=training_setB LIMIT=0 make challenge-2019
```

Comparators, setB ablation, miss attribution, primary-window bootstrap intervals, and the named
profile frontier:

```bash
make challenge-2019-paper-analyses
```

The command is a regression reproduction, not permission to retune on setB. Frozen inputs are
listed in [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

Patient-level source files and replay outputs remain outside version control. The reproducibility
manifest records code revision, artifact paths, content hashes, result scope, and prohibited claims.

## 8. Claim boundary

This manuscript supports a retrospective alert-governance claim on PhysioNet Challenge 2019. It
does not support any statement that Curie:

- diagnoses sepsis or another condition;
- improves mortality, organ failure, treatment time, or length of stay;
- works on MIMIC-IV, eICU, FHIR demo, SYN-ICU, Synthea, or a hospital feed;
- is clinically validated, production-ready, FDA-cleared, or suitable for patient care; or
- outperforms a clinical score, commercial product, or deployed workflow.

## References

1. Embi PJ, Leonard AC. Evaluating alert fatigue over time to EHR-based clinical trial alerts:
   findings from a randomized controlled study. *J Am Med Inform Assoc.* 2012;19:e145–e148.
   [doi:10.1136/amiajnl-2011-000743](https://doi.org/10.1136/amiajnl-2011-000743).
2. Elias P, Peterson E, Wachter B, Ward C, Poon E, Navar AM. Evaluating the impact of
   interruptive alerts within a health system: use, response time, and cumulative time burden.
   *Appl Clin Inform.* 2019;10:909–917.
   [doi:10.1055/s-0039-1700869](https://doi.org/10.1055/s-0039-1700869).
3. Downing NL, et al. Electronic health record-based clinical decision support alert for severe
   sepsis: a randomised evaluation. *BMJ Qual Saf.* 2019;28:762–768.
   [doi:10.1136/bmjqs-2018-008765](https://doi.org/10.1136/bmjqs-2018-008765).
4. Reyna MA, Josef CS, Jeter R, et al. Early Prediction of Sepsis From Clinical Data: The
   PhysioNet/Computing in Cardiology Challenge. *Crit Care Med.* 2020;48:210–217.
   [doi:10.1097/CCM.0000000000004145](https://doi.org/10.1097/CCM.0000000000004145).
5. Reyna M, Josef C, Jeter R, et al. Early Prediction of Sepsis from Clinical Data: The
   PhysioNet/Computing in Cardiology Challenge 2019. Version 1.0.0. PhysioNet; 2019.
   [doi:10.13026/v64v-d857](https://doi.org/10.13026/v64v-d857).
6. Vincent JL, Moreno R, Takala J, et al. The SOFA (Sepsis-related Organ Failure Assessment) score
   to describe organ dysfunction/failure. *Intensive Care Med.* 1996;22:707–710.
   [doi:10.1007/BF01709751](https://doi.org/10.1007/BF01709751).
7. Royal College of Physicians. *National Early Warning Score (NEWS) 2: Standardising the
   assessment of acute-illness severity in the NHS.* London: RCP; 2017.
8. Seymour CW, Liu VX, Iwashyna TJ, et al. Assessment of clinical criteria for sepsis: for the
   Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3). *JAMA.*
   2016;315:762–774. [doi:10.1001/jama.2016.0288](https://doi.org/10.1001/jama.2016.0288).
9. Bone RC, Balk RA, Cerra FB, et al. Definitions for sepsis and organ failure and guidelines for
   the use of innovative therapies in sepsis. *Chest.* 1992;101:1644–1655.
   [doi:10.1378/chest.101.6.1644](https://doi.org/10.1378/chest.101.6.1644).
