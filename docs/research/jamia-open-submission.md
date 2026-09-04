# Governing interruptions after deterministic deterioration scoring: a retrospective alert-policy evaluation on PhysioNet Challenge 2019

**Submission target:** JAMIA Open — Research and Applications
**Format budget:** ≤4,000 words main text · structured abstract ≤250 words · lay summary ≤200 words · ≤4 tables · ≤6 figures · references unlimited
**Reporting boundary:** retrospective offline evaluation on one public challenge; not clinical validation
**Results dataset:** PhysioNet/Computing in Cardiology Challenge 2019 v1.0.0 (CC-BY 4.0)

> Editor note (delete before submission): this is the condensed JAMIA Open version.
> Compiled paper: [`paper/main.tex`](../../paper/main.tex). Working markdown: [`paper/DRAFT.md`](../../paper/DRAFT.md).
> Tables regenerate from frozen JSON via `make paper-tables` (do not hand-copy metrics).

---

## Structured abstract

**Background and Significance:** Clinical deterioration scores and clinician interruptions are
different design objects: a threshold can identify a concerning state yet still generate repeated
or poorly timed pages. Governance rules applied after deterministic scoring may reduce interruptions
without changing the underlying score.

**Objectives:** To compare a frozen dual-lane governance policy on partial SOFA against
threshold-only partial SOFA and against hourly SIRS, NEWS2, and partial qSOFA, and to attribute the
effect to individual governance mechanisms on a locked Challenge 2019 holdout.

**Materials and Methods:** We replayed hourly Challenge 2019 records through a deterministic
partial-SOFA scorer, tuned governance on setA (20,336 stays), froze the rule bundle and timing
policy, and evaluated setB (20,000 stays) once. Detection used any governed emission within
[label_start−12 h, +6 h]; burden used interruptive emissions. We report stay-level bootstrap 95%
CIs (1,000 replicates, seed 42) and drop-one mechanism ablations without reselection.

**Results:** Governed partial SOFA matched threshold-only sensitivity (79.5%, 95% CI 77.0–81.8)
while the interruptive lane emitted 13.2% as many alerts (NNA 106.1, CI 96.2–116.6). Incomplete
NEWS2 and SIRS reached 76.0% and 78.5% but as ungoverned streams (NNA 163–213). Removing the
90-minute refractory interval doubled interruptive volume; removing the page gate raised
interruptive sensitivity to 44.6%.

**Discussion:** Governance shifted detection onto a passive lane and confined interruptions;
residual NNA remained high. Results reflect a proxy label and partial score.

**Conclusion:** A frozen governance policy reduced page-eligible emissions while retaining
retrospective detection. This does not establish diagnosis, clinical benefit, or external validity.

---

## Lay summary

Hospital early-warning systems often alert clinicians so frequently that important warnings get lost
among routine ones — a problem called alert fatigue. We studied whether the *decision to interrupt a
clinician* can be treated as a separate, tunable step that runs after a patient's risk score is
calculated, rather than alerting every time a score crosses a line. Using a public dataset of
intensive-care records, we set the rules on one half of the data, locked them, and tested them once
on the other half. The governed system flagged the same fraction of deteriorating patients as the
raw score (about four in five) but reduced the number of urgent, interruptive alerts to roughly an
eighth. Two rules did most of the work: a quiet period after each alert, and a gate that reserved
urgent alerts for stronger trajectories. The urgent-alert count was still high, so this is a
starting point, not a finished solution. Because the data use a proxy definition of illness and an
incomplete score, these results describe alert behaviour only — not a diagnosis, a clinical benefit,
or readiness for patient care.

---

## Background and Significance

Electronic clinical decision support frequently produces technically correct but operationally weak
interruptions. Repeated exposure reduces responsiveness, and many interruptive alerts are dismissed
within seconds, indicating that interruption cost depends on relevance and workflow fit rather than
alert count alone [1,2]. Sepsis-alert trials have produced mixed clinical results, reinforcing that a
score's discrimination does not by itself determine the value of the alerting workflow [3].

Most retrospective deterioration studies treat a positive rule or model output as *the alert*. We
instead separate two stages. A deterministic scorer first produces a complete, auditable signal. A
shared governance layer then decides whether that signal is suppressed, shown passively, or emitted
through an interruptive lane, using repeated crossings, temporal persistence, baseline-relative
change, refractory windows, and a page gate — none of which alter the clinical score. Framing
governance as a versioned, separable policy makes each interruption rule an object that can be frozen,
ablated, and reproduced, which is the methodological gap this paper addresses.

## Objectives

Using the PhysioNet/Computing in Cardiology Challenge 2019 hourly ICU dataset and its onset-aligned
`SepsisLabel` [4,5], we ask one narrow question: under a frozen setA-to-setB evaluation, can a shared
governance policy reduce page-eligible emissions relative to threshold-only partial SOFA while
retaining retrospective label detection — and which governance mechanism produces the effect? We do
not evaluate diagnosis, treatment, mortality, clinician adoption, MIMIC-IV performance, prospective
deployment, or regulatory readiness.

## Materials and Methods

### System boundary

The prototype projects clinical events onto a canonical envelope, transports them through Kafka, and
applies versioned deterministic rules in Apache Flink. Each scoring output carries the score,
severity, evidence identifiers, missing components, rule version, and rule-content hash. Shared
governance operates on this output and assigns passive or interruptive routing (Figure 1). An
optional language-model component may generate a *post-alert* narrative but cannot create, suppress,
escalate, or change an alert; it is therefore outside every result reported here. The retrospective
harness executes scoring and governance semantics directly and does not simulate clinician delivery,
acknowledgement, or treatment.

### Dataset and design

We used Challenge 2019 v1.0.0, comprising setA (20,336 stays) and setB (20,000 stays), released under
CC-BY 4.0 [4]. setA was used to select and freeze the operating point; setB was treated as a locked
retrospective holdout and was neither tuned nor reselected. This is not an official Challenge
submission and not an evaluation against the hidden Challenge test set; setB is a holdout within the
same public resource, not an external hospital cohort.

### Partial SOFA

SOFA summarizes organ dysfunction across six systems [6]. Challenge records support only a partial
reconstruction, using available oxygenation, mean arterial pressure, platelet, bilirubin, and
creatinine fields with causal forward-filling. The dataset omits Glasgow Coma Scale, urine-output
windows, vasopressor-dose ladders, and a reliable mechanical-ventilation flag; we therefore call the
signal **partial SOFA**, not complete SOFA and not a sepsis diagnosis. Missing inputs were never
imputed to reassuring values: the scorer recorded missing components and required at least two
scoreable components.

### Governance policy and comparators

The governance family contains five separable mechanisms: **crossings** (repeated qualifying score
crossings), **persistence** (a qualifying state held for a configured duration), **baseline delta**
(change from a recent patient baseline), **refractory interval** (suppression of repeated emissions),
and a **page gate** (reserving the interruptive lane for stronger trajectories while preserving a
passive watch lane). The setA-selected configuration used one crossing, no watch-path persistence,
baseline gating off, and a 90-minute refractory interval; its page gate required two crossings,
30 minutes of page persistence, a score increase ≥1 point, and ≥2 positive components.

At each hourly update the same partial-SOFA result fed **threshold-only** and **governed** paths.
Governed output was split into *any governed emission* (watch plus interruptive; used for detection)
and *interruptive emission* (page-eligible; used for burden and NNA). An interruptive emission is an
offline routing decision, not an episode-arbitrated or delivered page.

Independently of governance, we scored three hourly threshold-only bedside comparators on the same
stays and window: **SIRS ≥ 2** (temperature, heart rate, respiratory rate, white-cell count — all
present); **NEWS2 ≥ 5** with consciousness/AVPU absent and scored 0 (**incomplete NEWS2**) [7]; and
**partial qSOFA ≥ 2** using respiratory rate and systolic pressure, with the GCS limb omitted [8].
These comparators have no refractory window or page gate and place governed partial SOFA on a
detection/burden plane that is not merely "governance versus its own threshold." They are not a
claim of superiority to NEWS or qSOFA in practice [7,8,9].

### Operating-point freeze, labels, and timing

The selected candidate `grid_p0_r90_b0` was frozen as `p1_setA_winner.json`, bound to rule bundle
`sepsis-sofa.challenge2019-p1.v1.json`, and its content hash locked before setB evaluation. `SepsisLabel`
becomes positive approximately six hours before the Challenge clinical-onset definition [4]; we call
the first positive hour `label_start` and do not equate it with bedside onset. The primary timing
policy `window_m12_p6` counts a stay as detected if any qualifying emission occurs in
[label_start−12 h, +6 h]; mean lead time is measured from the first in-window governed emission to
`label_start`. Grace-0/6/12 h, early-only, and ±12 h definitions are secondary analyses.

### Outcomes and statistics

Primary holdout metrics were governed sensitivity, interruptive sensitivity, interruptive NNA
(interruptive emissions per interruptive true-positive stay), and bounded mean lead time. The
selection-split burden metric was interruptive divided by threshold-only emissions. Primary-window
95% CIs were stay-level percentile bootstrap intervals (1,000 replicates, seed 42). SetB ablation
dropped one frozen mechanism at a time and re-scored setB without reselection; variants whose knobs
already matched the winner are reported as null ablations. Governed false negatives were attributed
from replay rows. Golden fixtures, Python/Java parity checks, and a demo-schema leakage harness are
appendix methods evidence only and contribute no sensitivity estimate.

## Results

### Selection split

On setA (1,790 label-positive stays), the frozen operating point emitted 529,958 threshold-only and
64,928 interruptive alerts (ratio 0.123), with governed sensitivity 88.4% and interruptive
sensitivity 37.7%. These are selection results and are not substituted for the holdout.

### Primary setB holdout

Governed partial SOFA matched threshold-only detection at 79.5% while confining interruptions
(Table 1). The gap between governed (79.5%) and interruptive (34.0%) sensitivity is the intended
dual-lane behaviour: detection is preserved on a passive watch lane without turning every detection
into a page. The interruptive lane emitted 13.2% of threshold-only SOFA volume, but an interruptive
NNA of 106.1 indicates emission reduction alone did not yield a clinically efficient page stream.

**Table 1. Primary setB holdout (20,000 stays; `window_m12_p6`).**

| Metric | Result | 95% CI | Interpretation |
|---|---:|---:|---|
| Governed sensitivity | 79.5% | 77.0–81.8 | Any governed emission in-window |
| Interruptive sensitivity | 34.0% | 31.3–36.8 | Interruptive emission in-window |
| Interruptive NNA | 106.1 | 96.2–116.6 | Interruptive emissions per interruptive TP stay |
| Interruptive / naive emissions | 0.132 | 0.127–0.137 | Page-eligible vs threshold-only SOFA |
| Mean in-window lead | 5.97 h | 5.54–6.39 | First governed emission to `label_start` |

Stay-level percentile bootstrap, 1,000 replicates, seed 42.

### Bedside comparators

On the same holdout and window, incomplete NEWS2 and SIRS approached governed sensitivity but as
ungoverned hourly streams with far higher burden; partial qSOFA was specific and quiet because its
mentation limb is missing (Table 2). Governed partial SOFA is the only policy combining 79.5%
detection with materially reduced volume.

**Table 2. SetB bedside comparators versus Curie lanes (`window_m12_p6`).**

| Policy | Sensitivity | Emissions | NNA |
|---|---:|---:|---:|
| SIRS ≥ 2 | 78.5% | 191,294 | 213.3 |
| NEWS2 ≥ 5 (incomplete) | 76.0% | 141,629 | 163.2 |
| Partial qSOFA ≥ 2 | 24.9% | 22,068 | 77.7 |
| Threshold-only partial SOFA | 79.5% | 311,797 | 343.4 |
| Governed partial SOFA (any emit) | 79.5% | 159,933 | 176.1 |
| Interruptive governed lane | 34.0% | 41,158 | 106.1 |

NNA is emissions per in-window true-positive stay. NEWS2 omits consciousness; qSOFA omits GCS. Not a
superiority claim.

### Mechanism ablation

Dropping one frozen mechanism at a time localized the effect (Table 3). On hourly Challenge spacing,
zeroing page persistence (30 min) or relaxing page crossings (2→1) did not move setB metrics;
`drop_baseline` is null because the winner already disables baseline gating. The **90-minute
refractory interval** is what holds watch volume below naive SOFA (removing it moved the reduction
ratio 0.132→0.264), and the **page gate** is what holds interruptive sensitivity at 34.0% rather
than 44.6%.

**Table 3. SetB drop-one ablation of the frozen winner (`window_m12_p6`).**

| Variant | Gov sens | Int sens | Int reduction | Int NNA | Note |
|---|---:|---:|---:|---:|---|
| Frozen winner | 79.5% | 34.0% | 0.132 | 106.1 | Operating point |
| drop_baseline | 79.5% | 34.0% | 0.132 | 106.1 | Null (already off) |
| drop_persistence | 79.5% | 34.0% | 0.132 | 106.1 | No change on hourly rows |
| drop_crossings | 79.5% | 34.0% | 0.132 | 106.1 | No change on hourly rows |
| drop_refractory | 79.5% | 36.2% | 0.264 | 199.6 | Watch volume = naive |
| drop_page_gate | 79.5% | 44.6% | 0.208 | 127.5 | All emits interruptive |

### Miss attribution and timing robustness

Of 1,142 label-positive setB stays, 234 were governed false negatives under the primary window
(Table 4). Most misses (60.3%) never crossed the naive SOFA threshold in-window — a scorer limit,
not a governance limit — and no in-window miss was attributable to the refractory interval on the
frozen winner. Across five secondary timing definitions, naive and governed sensitivity were equal
for the frozen configuration (grace-0 h 56.3%; grace-6 h 81.1%; grace-12 h 84.6%; early-only 54.8%;
±12 h 83.3%) and the profile ranking (frozen ≈ dual ≈ accuracy > balanced > strict) was stable; the
81.1% grace-6 h value is secondary and not the primary result (Figure 4).

**Table 4. Governed false-negative attribution on setB (`window_m12_p6`; 234 of 1,142 positives).**

| Reason | Count | Rate |
|---|---:|---:|
| Never crossed naive SOFA threshold in-window | 141 | 60.3% |
| Governed emission only outside the window | 58 | 24.8% |
| Never scoreable (missing inputs) | 35 | 15.0% |

## Discussion

This study evaluates an alert policy rather than a new predictive model. Threshold-only comparisons
typically collapse score output, interface behaviour, and workflow into one binary alert; separating
scoring from governance makes persistence, crossings, refractory windows, and page gating
individually versionable and ablatable while the clinical score stays fixed. On the setB holdout,
incomplete NEWS2 and SIRS approached governed sensitivity but only as high-burden ungoverned streams,
and the ablation localizes the burden reduction to two mechanisms (refractory interval and page
gate) rather than the policy as a whole. That mechanism-level attribution — not the headline
79.5% — is the contribution.

The results support dual-lane design: retrospective detection can be represented passively while a
selective policy controls interruption. They do not show the interruptive lane is optimal; an
interruptive NNA of 106.1 (95% CI 96.2–116.6) is a substantial residual burden and a design target,
not something to hide behind the reduction ratio. The comparison to SIRS/NEWS2/qSOFA is a
Challenge-2019 detection/burden plane, not evidence that Curie outperforms those scores clinically.

**Limitations.** First, `SepsisLabel` is an onset-aligned proxy built for a prediction competition,
not prospective bedside adjudication, and begins ~6 h before the Challenge onset definition; reported
lead time is relative to `label_start`. Second, the score is partial SOFA, omitting GCS, urine
output, vasopressor ladders, and reliable ventilation context. Third, setB is a holdout within one
public challenge, not an external cohort; we estimate no transportability, calibration, distribution
shift, subgroup fairness, or prospective performance. Fourth, interruptive outputs are emission-level
page candidates — not episode-arbitrated, delivered, or clinician-reviewed — so NNA counts emissions,
not clinically necessary pages. Finally, fixture and demo-schema checks prove implementation
behaviour and reproducibility only, not a second clinical cohort.

**Future work.** The next evidence step is a pre-specified MIMIC-IV study using availability-time
replay, an explicitly partial or fuller SOFA reconstruction, Sepsis-3-aligned labels, and subgroup
analysis, followed — only later — by a silent prospective study to measure delivered burden,
clinician response, workflow fit, safety, and outcomes.

## Conclusion

On a locked PhysioNet Challenge 2019 holdout, a frozen dual-lane governance policy retained 79.5% of
threshold-only detection while emitting 13.2% as many page-eligible alerts, with the reduction
attributable to the refractory interval and page gate specifically. These findings concern
alert-policy behaviour against a proxy label and a partial score; they do not establish sepsis
diagnosis, clinical benefit, external validity, or safety for patient care.

## Figures

- **Figure 1.** System boundary: deterministic scoring → shared governance → passive/interruptive
  lanes, with the optional post-alert LLM narrative off the alert path (`figure_specs.v2.json:architecture_mermaid`).
- **Figure 2.** Cohort and operating-point flow: setA tune → freeze `p1_setA_winner` → setB primary
  window (`figure_specs.v2.json:cohort_flow_mermaid`).
- **Figure 3.** SetB detection/burden plane: in-window sensitivity (y) versus in-window emissions
  (x, log scale) for all six policies on one cohort and window — the three ungoverned bedside
  comparators, threshold-only SOFA, governed SOFA (watch + page), and the interruptive lane; NNA
  annotated per point. Governed SOFA holds threshold-only sensitivity (79.5%) at roughly half the
  emissions and sits up-and-left of incomplete NEWS2. Rendered
  [`figures/figure3_detection_burden.pdf`](../../eval/manuscript/generated/figures/figure3_detection_burden.pdf).
  (All points are setB `window_m12_p6`; we deliberately do not overlay the setA named-profile
  frontier here to avoid mixing cohorts — that frontier remains available as
  `figure_specs.v2.json:operating_point` for a supplementary figure.)
- **Figure 4.** SetB detection-definition robustness: naive versus governed sensitivity across the
  five secondary timing windows (equal for the frozen winner in every definition), with the primary
  `window_m12_p6` result (79.5%) marked. Rendered
  [`figures/figure4_timing_robustness.pdf`](../../eval/manuscript/generated/figures/figure4_timing_robustness.pdf).

## Data availability

Challenge 2019 v1.0.0 is publicly available from PhysioNet under CC-BY 4.0 [5]; patient-level source
files and replay outputs are not redistributed. All frozen operating points, timing policies, rule
bundles, comparator/ablation/miss/bootstrap sidecars, content hashes, and the reproducibility
manifest are committed. Analyses regenerate with `make challenge-2019-paper-analyses`; the
supplementary reproducibility package builds with `make manuscript`. Frozen inputs:
`p1_setA_winner.json`, `timing_primary.v1.json`, `holdout_primary_window_m12_p6.v2.json`,
`comparators_setB_window_m12_p6.v1.json`, `ablation_setB_window_m12_p6.v1.json`, `miss_analysis.v2.json`,
`pareto_named_profiles.v1.json`, `robustness_summary.v1.json`, `sepsis-sofa.challenge2019-p1.v1.json`,
and `reproducibility_manifest.v2.json`.

## References

1. Embi PJ, Leonard AC. Evaluating alert fatigue over time to EHR-based clinical trial alerts. *J Am
   Med Inform Assoc.* 2012;19:e145–e148. doi:10.1136/amiajnl-2011-000743.
2. Elias P, Peterson E, Wachter B, Ward C, Poon E, Navar AM. Evaluating the impact of interruptive
   alerts within a health system. *Appl Clin Inform.* 2019;10:909–917. doi:10.1055/s-0039-1700869.
3. Downing NL, et al. Electronic health record-based clinical decision support alert for severe
   sepsis: a randomised evaluation. *BMJ Qual Saf.* 2019;28:762–768. doi:10.1136/bmjqs-2018-008765.
4. Reyna MA, Josef CS, Jeter R, et al. Early Prediction of Sepsis From Clinical Data: The
   PhysioNet/Computing in Cardiology Challenge. *Crit Care Med.* 2020;48:210–217.
   doi:10.1097/CCM.0000000000004145.
5. Reyna M, Josef C, Jeter R, et al. Early Prediction of Sepsis from Clinical Data: The
   PhysioNet/Computing in Cardiology Challenge 2019. Version 1.0.0. PhysioNet; 2019.
   doi:10.13026/v64v-d857.
6. Vincent JL, Moreno R, Takala J, et al. The SOFA (Sepsis-related Organ Failure Assessment) score.
   *Intensive Care Med.* 1996;22:707–710. doi:10.1007/BF01709751.
7. Royal College of Physicians. *National Early Warning Score (NEWS) 2.* London: RCP; 2017.
8. Seymour CW, Liu VX, Iwashyna TJ, et al. Assessment of clinical criteria for sepsis (Sepsis-3).
   *JAMA.* 2016;315:762–774. doi:10.1001/jama.2016.0288.
9. Bone RC, Balk RA, Cerra FB, et al. Definitions for sepsis and organ failure. *Chest.*
   1992;101:1644–1655. doi:10.1378/chest.101.6.1644.
