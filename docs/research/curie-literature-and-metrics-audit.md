# Curie literature & metrics audit (read-only)

**Status:** audit only — no production code, scoring code, replay code, frozen artifacts,
paper tables, or generated results were modified.
**Scope:** `paper/DRAFT.md`, `docs/research/mimic-iv-study-protocol.md`,
`docs/research/clinical-validation.md`, supporting contracts and scorer code in the
`codex/curie-literature-v2` worktree.
**Worktree:** `/Users/srirammentey/AI/curie-literature` (`codex/curie-literature-v2`)
**Commit audited:** `62be462d68fcc4ba09dd0ffeecd891108bb6ab42` (`chore: checkpoint review baseline`)
**Date:** 2026-09-05

Primary sources were fetched and verified on 2026-09-05; direct links are given per item and
in [Sources](#sources). Verification of the pinned mimic-code SQL is byte-level (SHA-1 blob +
SHA-256 recomputed locally, see §9).

---

## 1. Original SOFA timing and worst-value semantics

**Verified fact (correct claim):**
The original SOFA score (Vincent et al., *Intensive Care Med* 1996;22:707–710) is calculated
**at ICU admission and every 24 h thereafter**, and each of the six sub-scores uses the
**most severe (worst) value of each variable during the preceding 24-hour period**. The
original 1996 full text is paywalled with no open-access copy and no abstract on PubMed, so
the canonical wording is verified via two accessible authoritative sources:

- Lambden et al., *Crit Care* 2019;23:374 (open access):
  > "SOFA score may traditionally be calculated on admission to ICU and at each 24-h period
  > that follows." and "The value for each sub-score that represents the most severe (worst)
  > value for the respective 24-h period for each parameter was used in initial validation
  > and subsequent clinical studies using the SOFA score."
- The pinned mimic-code `sofa.sql` (see §9) computes hourly scores with a 24-hour rolling
  window (`MAX(...) OVER w` over the last 24 hours; header: "the calculation window is
  24 hours").

**What Curie actually does (deviation, not stated explicitly in DRAFT §3.2):**
`eval/sofa/scoring.py::compute_sofa_score` is a **point-in-time** scorer: it scores the
current (forward-filled) values with no 24-hour worst-value window. The Challenge loader
(`ingestion/adapters/challenge2019/loader.py`) forward-fills the last observation per
variable. Forward-fill approximates "most recent observed," **not** "worst in preceding
24 h." The frozen MIMIC protocol (§5) also uses event-driven scoring, which will diverge
from the pinned mimic-code `sofa.sql` 24-hour-window scores.

**Corrected claim / recommendation:**
- Keep calling the score "partial SOFA," and add one sentence in DRAFT §3.2 (Methods):
  "The original SOFA convention scores the worst value of each variable over the preceding
  24 h; our replay scores the point-in-time forward-filled values, so hourly scores are not
  directly comparable to daily worst-in-24 h SOFA values."
- MIMIC protocol: pre-specify which SOFA convention feeds `sepsis3_onset` (mimic-code
  24-hour windows) vs. the Curie scorer (point-in-time), and capture the divergence under
  CON-1 in the claims ledger.

**Uncertain:** the exact 1996 sentence ("calculated at admission and every 24 h…") could not
be verified verbatim from the paywalled primary; cite Lambden 2019 or Vincent 1996 with
institutional access if a verbatim quote is needed.

## 2. Mechanical-ventilation requirement for respiratory SOFA points 3 and 4

**Verified fact (correct claim):**
In the original SOFA respiratory component, points **3 and 4 require respiratory support**:
PaO2/FiO2 <200 with respiratory support = 3; <100 with respiratory support = 4; points 1–2
(<400, <300) have no support requirement. Verified via the Sepsis-3 reproduction of the SOFA
table (Singer et al., *JAMA* 2016;315:801–810, Table 1):
> "Respiration — PaO2/FIO2, mm Hg: ≥400 [0]; <400 [1]; <300 [2]; **<200 with respiratory
> support** [3]; **<100 with respiratory support** [4]"
and Lambden 2019: "The SOFA score calls for patients to receive a score of 3 or 4 if they
reach a PaO2/FiO2 ratio of less than 200 or less than 100 respectively and are receiving
respiratory support."

**What Curie does:** `eval/sofa/scoring.py::score_respiration` requires
`mechanically_ventilated=True` for points 3–4 (thresholds `<200`/`<100` from
`eval/sofa/thresholds.py`) — consistent with the original, with the nuance that "mechanical
ventilation" is a **stricter** operationalization than "respiratory support" (the pinned
mimic-code `sofa.sql` uses `ventilation_status = 'InvasiveVent'` the same way). On Challenge
2019 the loader hardcodes `mechanically_ventilated=False` (`loader.py`), so the respiration
component can never reach 3–4 there — the DRAFT and `challenge-2019-eval.md` state this
honestly.

**Correction to flag:** `eval/respiratory/scoring.py::stage_from_oxygenation` (the
`resp-deterioration` indicator, not SOFA) assigns **stage 3 for ratio <100 regardless of
ventilation** and stage 3 for ratio <200 only if ventilated. This is an internal
inconsistency with the SOFA respiratory rule; document it in the respiratory contract if the
two are ever compared.

**Recommended wording (if quoted in a paper):** "Respiratory SOFA points 3–4 require
mechanical ventilation (operationalizing the original 'with respiratory support' qualifier);
the Challenge 2019 loader cannot set this flag, so partial SOFA respiration is capped at
2 points there."

## 3. Rice and Pandharipande S/F-to-P/F conversion claims

**Finding: no Rice/Pandharipande claim exists in this worktree** (grep across `docs/`,
`paper/`, `eval/` finds none). What exists is an **unimputed** use of SpO2/FiO2:
`eval/sofa/scoring.py::effective_resp_ratio` and
`eval/respiratory/scoring.py::effective_resp_ratio` divide SpO2 by FiO2 and apply the **P/F
cutoffs** (400/300/200/100) to the raw S/F ratio. That is a raw proxy, **not** the validated
conversion.

**Verified facts (correct claims if the conversion is ever cited):**
- Rice et al., *Chest* 2007;132(2):410–7 (PMID **17573487**, doi:10.1378/chest.07-0617):
  ARDSNet ALVEOLI patients; S/F = 64 + 0.84×(P/F); **S/F 235 ↔ P/F 200, S/F 315 ↔ P/F 300**;
  SpO2 values restricted to ≤97%. (S/F 235: 85% sens / 85% spec for P/F <200; S/F 315:
  91% sens / 56% spec for P/F <300.)
- Pandharipande et al., *Crit Care Med* 2009;37(4):1317–21 (PMID **19242333**,
  doi:10.1097/CCM.0b013e31819cefa9): log(PF) = 0.48 + 0.78×log(SF); SOFA respiratory
  imputation **S/F <512 → P/F 400, <357 → 300, <214 → 200, <89 → 100**; derived from 4,728
  matched measurements (Vanderbilt anesthesia + ARMA), SpO2 ≤98%; validated in 100
  trauma/surgical ICU patients (Spearman ρ 0.85 vs SOFA–PF).
- Lambden et al. 2019 (respiratory component): for SpO2-based scoring, "there is not
  sufficient evidence base to recommend this approach at this stage."

**Corrected claim / recommendation:** If any manuscript text implies the S/F usage is a
validated S/F→P/F conversion, that is unsupported. Either (a) prefer PaO2/FiO2; (b) when only
SpO2 is available, apply the Pandharipande 2009 imputation thresholds and cite it; or (c)
explicitly call the raw SpO2/FiO2 ratio an **unvalidated proxy**. Option (c) is what the
code currently does; the paper must say so.

## 4. Sepsis-3 AUROC/qSOFA attribution and exact population

**Finding:** `paper/DRAFT.md` makes **no AUROC claims** and correctly cites Seymour et al.
2016 (ref 8) for Sepsis-3 definitions. If any downstream text attributes discrimination
numbers, the verified facts are:

- qSOFA definition (Singer Box 4 / Seymour): respiratory rate ≥22/min; altered mentation
  (GCS ≤13 in the derivation model; generalized to "altered mentation" in the final
  definition, P=0.55 for the change); systolic BP ≤100 mm Hg. Threshold **≥2**.
- Derivation population: 1.3M EHR encounters 2010–2012 at 12 UPMC community+academic
  hospitals; **148,907 encounters with suspected infection** (74,453 derivation / 74,454
  validation), 4% died.
- Validation AUROCs for **in-hospital mortality** (abstract, verbatim):
  - Non-ICU: **n = 66,522** suspected-infection encounters; **qSOFA AUROC 0.81**
    (95% CI 0.80–0.82) vs SOFA 0.79 (0.78–0.80) vs **SIRS 0.76** (0.75–0.77).
  - ICU: **n = 7,932**; **SOFA AUROC 0.74** (0.73–0.76) vs qSOFA 0.66 (0.64–0.68) vs
    SIRS 0.64 (0.62–0.66); LODS 0.75.
- Sepsis-3 sepsis criterion: acute change in total SOFA ≥2 consequent to infection
  (Singer 2016). qSOFA is a **non-ICU** prompt; it is statistically inferior to SOFA inside
  the ICU.

**Attribution note:** DRAFT's comparator is "partial qSOFA ≥2 using RR and SBP, GCS limb
omitted" — correctly labeled. With only two limbs, ≥2 requires both limbs, which the DRAFT
states. No correction needed beyond citing the correct population if numbers are ever added.

## 5. PhysioNet Challenge 2019 metrics — comparability to Curie's metrics

**Verified facts:**
- Official metric is the **normalized clinical utility score (UTW)**, not
  sensitivity/NNA: predictions between **12 h before and 3 h after t_sepsis** are rewarded
  (maximum reward at t_sepsis − 6 h); predictions >12 h before onset, missed predictions,
  and false alarms on non-septic patients are penalized. Winners were scored on a hidden
  test set of 24,819 patients across systems A/B/C (paper §2.3; PhysioNet page).
- SepsisLabel definition: **label = 1 for t ≥ t_sepsis − 6 h** (i.e., the six hours
  *preceding* clinical onset plus everything after); 0 otherwise. Both the PhysioNet page
  ("SepsisLabel is 1 if t ≥ t_sepsis − 6 and 0 if t < t_sepsis − 6") and the paper
  (Table 1 row 41) state this. **The DRAFT's claim "the Challenge label begins approximately
  six hours before its clinical-onset definition" is TRUE** — tighten "approximately" to
  "exactly six hours before (t ≥ t_sepsis − 6 h)".
- Public set sizes verified: **setA 20,336** and **setB 20,000** (40,336 total).
  License **CC BY 4.0** verified on the PhysioNet page.
- Clinical onset: Sepsis-3 (suspected infection = IV antibiotics + cultures with
  **directional** windows — antibiotics first ⇒ cultures within 24 h; cultures first ⇒
  antibiotics within 72 h; ≥72 h consecutive antibiotics; plus acute SOFA rise ≥2;
  t_sepsis = min(t_suspicion, t_SOFA) with t_SOFA within [t_suspicion−24 h, t_suspicion+12 h]).

**Comparability verdict:** Curie's metrics (governed sensitivity in
`[label_start−12 h, label_start+6 h]`, interruptive NNA, reduction ratio) are **not
comparable** to the official utility score and cannot be placed on the leaderboard.
The DRAFT already disclaims this ("not an official Challenge submission"), which is correct.
Arithmetic worth stating once in the paper: because the label is shifted 6 h ahead, the
primary window equals **[t_sepsis − 18 h, t_sepsis]** in clinical-onset time — detection
"after label_start" (up to +6 h) is still prediction at or before clinical onset, and the
"12 h early" window is really 18 h early relative to clinical onset. Also note hidden-test
structure: setB is a public training split, not the sequestered test — the DRAFT says this
correctly.

## 6. COMPOSER citation, year, venue, PPV, and lead-time claims

**Finding:** no COMPOSER citation exists in this worktree (single mention in
`docs/implementation-backlog.md` CURIE-040 as a product-landscape item, no numbers).

**Verified facts (correct citation if it is ever cited):**
- Shashikumar SP, Wardi G, Malhotra A, Nemati S. "Artificial intelligence sepsis prediction
  algorithm learns to say 'I don't know.'" **npj Digital Medicine. 2021;4(1):134**.
  doi:10.1038/s41746-021-00504-6 (PMID 34504260).
- Study design: **retrospective** train/test (80/20), temporal, and external validation
  (515,720 patients; UCSD Health + Emory; ICU + ED). The 2021 paper is **not** a
  prospective clinical validation — it states prospective trials are future work.
- Reported performance (sequential-prediction policy, alarm silenced 6 h after firing,
  true alarm = fire within 4–48 h before onset):
  - AUROC: ICU 0.925–0.953; ED 0.938–0.945 (internal/temporal/external).
  - **PPV at 80% sensitivity**: internal ICU 38.0%, ED 20.1%; temporal ICU 35.5%,
    ED 20.8%; external ICU 24.3%, ED 13.4%. (Hourly-window sepsis prevalence ~3–4% ICU,
    2–5.5% ED.)
  - Early warning (median [IQR]) before first antibiotics order: **ICU 12.2 [3.2–22.8] h;
    ED 2.1 [0.8–4.5] h**.
- Not FDA-cleared. A later deployment study is a QI quasi-experiment at two UCSD EDs:
  Boussina A, et al. "Impact of a deep learning sepsis prediction model on quality of care
  and survival." *npj Digit Med*. 2024;7(1):14 (1.9% absolute in-hospital sepsis-mortality
  reduction; not a regulatory clearance).
- Algorithm precursor: Shashikumar et al. "DeepAISE…" *Artif Intell Med*. 2021;113:102036.

**Corrected claim:** any future text that says "COMPOSER prospective PPV/lead time" must
cite the 2024 QI study (PPV from the 2021 retrospective paper), and "prospective validation"
is not supported by the 2021 paper.

## 7. Metric definitions (as used or proposed in this repo)

- **AUROC** — area under the ROC curve; equals the probability that a randomly chosen
  positive case ranks above a randomly chosen negative case. Summarizes discrimination
  across all thresholds; prevalence-independent but threshold-free, so it does not directly
  describe operational alert quality. (Fawcett, *Pattern Recogn Lett* 2006;27:861–874.)
- **AUPRC** — area under the precision–recall curve; informative under class imbalance and
  reflects PPV/FPR trade-off at fixed prevalence; no fixed 0.5 chance baseline (chance ≈
  outcome prevalence). (Saito & Rehmsmeier, *PLoS One* 2015;10(3):e0118432.)
- **PPV** — TP/(TP+FP) among emitted alerts in a defined unit (stay or emission-hour);
  depends on prevalence. For sensitivity s, prevalence p, false-alert rate f:
  PPV = s·p/(s·p + f·(1−p)). Must state the unit and horizon.
- **False-alert rate** — proportion of alerts on label-negative units (stay-level: alerted
  non-sepsis stays / non-sepsis stays; emission-level: non-sepsis alert hours per
  hour-at-risk) or alerts per 100 patient-days. Define the denominator explicitly.
- **NNA** (number needed to alert) — alerts emitted per true-positive detection
  (alerts/TP). In Curie, **emission-based and stay-level**: interruptive emissions per
  interruptive-true-positive stay (not episodes, not delivered pages). Historical pitfall
  recorded in `challenge-2019-eval.md`: pages/any-governed-TP (~44) vs pages/interruptive-TP
  (~94.2) — always quote the latter definition.
- **Lead time** — onset − first true-positive alert. Curie reports the **bounded** in-window
  lead time (first alert inside `[label_start−12 h, +6 h]`), which caps lead at 12 h and
  admits "negative lead" (first alert after label_start); the legacy unbounded ~42 h figure
  is a different quantity. Both must be labeled; the 5.97 h primary figure is bounded and
  relative to label_start, not clinical onset.
- **Episode-level vs stay-level detection** — stay-level: ≥1 qualifying alert in the window
  marks the stay detected. Episode-level: alerts are deduplicated/arbitrated into a single
  clinical episode (CURIE-012 in product) before counting. The Challenge replay used
  **stay-level, emission-level** detection; episode arbitration was explicitly not applied
  (DRAFT §3.3/§6), so Curie's NNA and sensitivities are not episode metrics. The MIMIC
  protocol adds `episode_count_per_100_patient_days` and
  `false_episode_rate_on_label_negative_stays` as secondary endpoints — these need the
  episode arbitrator to be wired first.

## 8. Is DCA appropriate for deterministic SOFA/governance outputs?

**Verdict: not directly.** Decision curve analysis (Vickers & Elkin, *Med Decis Making*
2006;26(6):565–74, PMC2577036) requires a model output interpreted as a **probability/risk**
at each **threshold probability p_t**; net benefit =
TP/n − FP/n × (p_t/(1−p_t)) is plotted against p_t and compared with treat-all/treat-none.
A deterministic SOFA score is not a calibrated risk: plotting net benefit against *score
thresholds* breaks the p_t interpretation (the x-axis maps to relative harms), and
governance outputs (watch/interruptive) are routing decisions, not risk estimates.

**Required target to make DCA valid:** a **calibrated probability of a pre-specified outcome
within a fixed horizon** — e.g., P(sepsis-3 onset within 24 h | observations so far), or
P(hospital mortality) — obtained by recalibrating the deterministic score (logistic or
isotonic recalibration fitted on a development/calibration split, evaluated on the locked
test split), then running DCA over a clinically justified p_t range. Without that
calibration target, DCA should not appear in the Challenge paper; detection/burden metrics
(sensitivity, NNA, reduction ratio) are the appropriate evaluation for the governance
claim. If a MIMIC DCA is added later, pre-specify the outcome, horizon, calibration method,
and p_t range in the protocol (currently absent from `mimic-iv-study-protocol.md`).

## 9. Do the protocol's MIMIC Sepsis-3 and KDIGO descriptions match the pinned mimic-code SQL?

**Pin integrity: VERIFIED.** `eval/mimic_study/labels/sources.json` pins
MIT-LCP/mimic-code commit `303d26c623dcc9c49cc0f204468d4acc2f063797` (exists upstream;
2026-09-01 merge). I downloaded all six files from that commit and recomputed both the git
blob SHA-1 and file SHA-256: **all six match sources.json byte-for-byte**
(sepsis3.sql, suspicion_of_infection.sql, kdigo_creatinine.sql, kdigo_stages.sql,
kdigo_uo.sql, sofa.sql). One bookkeeping bug: the `remote_path` values omit the
intermediate directories (`mimic-iv/concepts_postgres/sepsis/sepsis3.sql`, not
`.../sepsis3.sql`; same for `organfailure/` and `score/`) — the paths as written return 404.

**Sepsis-3 label — NOT an exact match to the protocol wording.** Protocol
(`protocol.v1.json` labels.primary_event):
"Sepsis-3-aligned: suspected infection + acute SOFA rise >= 2 from baseline within infection
window (mimic-code concept pin)", onset = "availability-time of the observation that first
completes the phenotype." The pinned `sepsis3.sql` actually does:
1. suspected infection = IV antibiotic **and** culture with directional windows (culture ≤72 h
   before abx, or culture ≤24 h after abx; positive culture preferred);
2. `sofa_24hours >= 2` — an **absolute** score with **baseline implicitly assumed 0** (the
   SQL comment says exactly this); it does **not** compute a delta from a measured baseline;
3. SOFA window validity: sofa `endtime` within [suspected_infection_time − 48 h,
   +24 h], where `sofa_24hours` is a **24-hour worst-value window** (pinned `sofa.sql`);
4. onset row = earliest by (suspected_infection_time, antibiotic_time, culture_time,
   endtime); the reported `sofa_time` is the **end** of the 24 h SOFA window.

So "acute SOFA rise ≥2 from baseline" describes Sepsis-3 (Singer 2016), not the pinned SQL,
and "availability-time of the observation that first completes the phenotype" ≠
`suspected_infection_time` (earlier of culture/antibiotic time) with a sofa window ending
up to 24 h later.

**Recommended wording (protocol labels section):**
"`sepsis3_onset` = mimic-code `sepsis3` concept (pinned commit `303d26c6…`, file
`mimic-iv/concepts_postgres/sepsis/sepsis3.sql`): suspected infection (IV antibiotic +
culture within the mimic-code directional 72 h/24 h windows) with `sofa_24hours ≥ 2`
(baseline assumed 0, per the pinned SQL) whose 24 h SOFA window ends within
[suspected_infection_time − 48 h, +24 h]; onset time = `suspected_infection_time` of the
earliest qualifying row. This operationalizes, but is not identical to, the Sepsis-3
'acute SOFA rise ≥2 from baseline' definition."

**KDIGO label — aligned in spirit, NOT an exact match.** Protocol:
"KDIGO stage >= 1 by creatinine and/or covered UO (align with aki-kdigo v0.4 timeline)."
The pinned `kdigo_stages.sql` uses: creatinine stages with baselines = **lowest creatinine
in prior 7 days / 48 hours**, including ≥0.3 mg/dL rise in 48 h and **≥4.0 mg/dL only with
a qualifying acute rise**; UO stages require **weight-based rates** over documented
windows (6/12/24 h); **CRRT → stage 3**; combined by GREATEST with a **6-hour
carry-forward smoothing**. The protocol wording omits CRRT, the baseline definitions, and
smoothing; "covered UO" is Curie aki-contract terminology (coverage ≥ window length), not
mimic-code's "documented hours" requirement. Also note one real semantic divergence:
Curie's `aki-contract` assigns stage 3 for "Cr ≥ 4.0 mg/dL **or** RRT" unconditionally,
whereas mimic-code requires the acute-rise qualifier for the ≥4.0 path. Capture this in
CON-1 or the protocol's missingness/special-handling section.

**Recommended wording:** "`aki_kdigo_stage_ge_1` = KDIGO stage ≥1 per mimic-code
`kdigo_stages` (pinned commit, creatinine 7-day/48-hour baselines + weight-based UO rate
windows + CRRT→3, 6 h smoothing); divergences from the aki-kdigo v0.4 timeline
(≥4.0-without-acute-rise, UO coverage rule) are documented in CON-1."

**Verdict on the audit question:** the descriptions are directionally correct but do **not**
exactly match the pinned SQL; amend the protocol wording as above (or keep the wording and
add the explicit operational details) before Stage B label generation.

## 10. Unsupported or overstated claims in `paper/DRAFT.md`

The draft is unusually well hedged. Specific findings:

| # | Location | Claim | Verdict / correction |
|---|---|---|---|
| 1 | Intro ¶1 | "Sepsis-alert trials have also produced mixed clinical results" [3] | **Overstated for one citation.** Ref [3] (Downing, BMJ Qual Saf 2019) is a single trial. Either make it singular ("A sepsis-alert trial…") or add ≥1 more trial citation. |
| 2 | Abstract & §3.5 | "The Challenge label begins **approximately** six hours before its clinical-onset definition" | Verified **true**, but it is **exactly** 6 h (label=1 for t ≥ t_sepsis − 6 h). Tighten wording and cite the PhysioNet page + paper Table 1. |
| 3 | §3.3 | SIRS comparator described as "SIRS (≥2) using temperature, heart rate, respiratory rate, and white-cell count" with no "incomplete" qualifier | **Under-flagged.** Bone 1992 SIRS includes PaCO2 <32 mmHg (RR limb) and >10% band forms (WBC limb); Challenge 2019 has neither, so this is *incomplete SIRS* too. Label it like the NEWS2/qSOFA comparators. |
| 4 | §3.2 | Replay uses "causal forward filling" without stating the deviation from 24 h worst-value SOFA | Add the clarifying sentence from §1 of this audit (point-in-time vs worst-in-24 h). |
| 5 | §3.3 | "NEWS2 ≥ 5 (Royal College of Physicians medium trigger)" | Verified: 5–6 = medium (urgent review), ≥7 = high (RCP NEWS2 2017). Implementation includes the +2 supplemental-oxygen weighting (FiO2 > 0.21) and SpO2 Scale 1; consciousness scored 0. Correctly labeled "incomplete NEWS2." No change needed beyond noting FiO2-based oxygen inference. |
| 6 | §3.5 / §6 | "Reported lead time is therefore relative to label_start, not proof of six hours of actionable clinical warning" | Correct and appropriately cautious. Optionally add the arithmetic from §5 (window = [t_sepsis − 18 h, t_sepsis] in clinical-onset time). |
| 7 | §3.1 | "…lists the files under the Creative Commons Attribution 4.0 International license" | Verified (PhysioNet page). OK. |
| 8 | §3.1 | setA "20,336 stays", setB "20,000 stays" | Verified against paper Table 2 and PhysioNet page. OK. |
| 9 | §2.1 / Abstract | LLM "cannot create, suppress, escalate, or change an alert" | Consistent with AGENTS.md hard rules. OK. |
| 10 | §4.2 / §5.1 | "Frozen governed partial SOFA matched threshold-only SOFA sensitivity at 79.5%" and ablation claims | Frozen-artifact results (sidecars). Not re-derived in this audit; the audit does not challenge frozen numbers, only their interpretation, which is hedged. OK. |
| 11 | References | Refs 1–9 bibliographic details | Spot-checked: Embi 2012 JAMIA, Elias 2019 ACI, Downing 2019 BMJ Qual Saf, Reyna 2020 CCM (doi 10.1097/CCM.0000000000004145 — note correct PMID is **31939789**), Vincent 1996, Seymour 2016, Bone 1992 all real and correctly formatted. OK. |

No unsupported claims of clinical validity, superiority, or utility-score comparability were
found in `DRAFT.md`; the claim boundary (§8) and limitations (§6) are aligned with the
repo's hard rules.

---

## Sources

Verified 2026-09-05.

1. Lambden S, Laterre PF, Levy MM, Francois B. The SOFA score—development, utility and
   challenges of accurate assessment in clinical trials. *Crit Care.* 2019;23(1):374.
   https://ccforum.biomedcentral.com/articles/10.1186/s13054-019-2663-7 (open access;
   quotes in §1 and §2)
2. Vincent JL, Moreno R, Takala J, et al. The SOFA (Sepsis-related Organ Failure
   Assessment) score to describe organ dysfunction/failure. *Intensive Care Med.*
   1996;22(7):707–710. doi:10.1007/BF01709751 (paywalled; no OA copy or abstract —
   timing sentence not verifiable verbatim; use Lambden 2019)
3. Singer M, Deutschman CS, Seymour CW, et al. The Third International Consensus
   Definitions for Sepsis and Septic Shock (Sepsis-3). *JAMA.* 2016;315(8):801–810.
   doi:10.1001/jama.2016.0287 — https://pmc.ncbi.nlm.nih.gov/articles/PMC4968574/
   (SOFA table with "with respiratory support" rows; sepsis definition; baseline-SOFA-zero
   assumption)
4. Seymour CW, Liu VX, Iwashyna TJ, et al. Assessment of clinical criteria for sepsis…
   (Sepsis-3). *JAMA.* 2016;315(8):762–774. doi:10.1001/jama.2016.0288 —
   https://pmc.ncbi.nlm.nih.gov/articles/PMC5433435/ (qSOFA definition, derivation
   population, validation AUROCs and n)
5. Rice TW, Wheeler AP, Bernard GR, et al. Comparison of the SpO2/FiO2 ratio and the
   PaO2/FiO2 ratio in patients with acute lung injury or ARDS. *Chest.* 2007;132(2):410–417.
   doi:10.1378/chest.07-0617 — https://pubmed.ncbi.nlm.nih.gov/17573487/ (S/F 235↔200,
   315↔300; SpO2 ≤97%)
6. Pandharipande PP, Shintani AK, Hagerman HE, et al. Derivation and validation of
   SpO2/FiO2 ratio to impute for PaO2/FiO2 ratio in the respiratory component of the
   Sequential Organ Failure Assessment score. *Crit Care Med.* 2009;37(4):1317–1321.
   doi:10.1097/CCM.0b013e31819cefa9 — https://pmc.ncbi.nlm.nih.gov/articles/PMC3776410/
   (S/F 512/357/214/89 imputation; 4,728 matched measurements; SpO2 ≤98%)
7. Reyna MA, Josef CS, Jeter R, et al. Early Prediction of Sepsis From Clinical Data: The
   PhysioNet/Computing in Cardiology Challenge. *Crit Care Med.* 2020;48(2):210–217.
   doi:10.1097/CCM.0000000000004145 (PMID 31939789) — and PhysioNet project page
   https://physionet.org/content/challenge-2019/ (SepsisLabel = 1 for t ≥ t_sepsis − 6 h;
   set sizes 20,336/20,000; CC BY 4.0; utility-score windows)
8. Shashikumar SP, Wardi G, Malhotra A, Nemati S. Artificial intelligence sepsis prediction
   algorithm learns to say "I don't know." *npj Digit Med.* 2021;4(1):134.
   doi:10.1038/s41746-021-00504-6 — https://www.nature.com/articles/s41746-021-00504-6
   (COMPOSER AUC/PPV/lead-time; retrospective design)
9. Boussina A, et al. Impact of a deep learning sepsis prediction model on quality of care
   and survival. *npj Digit Med.* 2024;7(1):14. doi:10.1038/s41746-023-00986-6
   (UCSD ED deployment QI study)
10. KDIGO AKI Work Group. KDIGO Clinical Practice Guideline for Acute Kidney Injury.
    *Kidney Int Suppl.* 2012;2(1):1–138.
    https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-AKI-Guideline-English.pdf
    (stage 1/2/3 creatinine and UO criteria)
11. Vickers AJ, Elkin EB. Decision curve analysis: a novel method for evaluating prediction
    models. *Med Decis Making.* 2006;26(6):565–574. doi:10.1177/0272989X06295361 —
    https://pmc.ncbi.nlm.nih.gov/articles/PMC2577036/ (net benefit definition;
    threshold-probability requirement)
12. Royal College of Physicians. National Early Warning Score (NEWS) 2. London: RCP; 2017.
    https://www.rcplondon.ac.uk/resources/national-early-warning-score-news-2/
    (aggregate 0–4 low / 5–6 medium / ≥7 high; +2 oxygen weighting; SpO2 Scales 1 and 2)
13. Bone RC, Balk RA, Cerra FB, et al. Definitions for sepsis and organ failure…
    *Chest.* 1992;101(6):1644–1655. doi:10.1378/chest.101.6.1644 (SIRS criteria;
    full text paywalled — criteria cross-checked via
    https://www.ncbi.nlm.nih.gov/books/NBK547669/)
14. Fawcett T. An introduction to ROC analysis. *Pattern Recogn Lett.* 2006;27(8):861–874.
    doi:10.1016/j.patrec.2005.10.010 (AUROC)
15. Saito T, Rehmsmeier M. The precision-recall plot is more informative than the ROC plot
    when evaluating binary classifiers on imbalanced datasets. *PLoS One.*
    2015;10(3):e0118432. doi:10.1371/journal.pone.0118432 (AUPRC)
16. MIT-LCP/mimic-code, commit `303d26c623dcc9c49cc0f204468d4acc2f063797`:
    `mimic-iv/concepts_postgres/{sepsis/sepsis3.sql, sepsis/suspicion_of_infection.sql,
    organfailure/kdigo_creatinine.sql, organfailure/kdigo_stages.sql,
    organfailure/kdigo_uo.sql, score/sofa.sql}` —
    https://github.com/MIT-LCP/mimic-code/commit/303d26c623dcc9c49cc0f204468d4acc2f063797
    (files re-downloaded and hash-verified against
    `eval/mimic_study/labels/sources.json` during this audit)

---

## Uncertain / unverifiable items (for follow-up)

1. Vincent 1996 verbatim timing sentence — paywalled, no OA copy, no PubMed abstract.
   Cite Lambden 2019 instead, or check via institutional access.
2. Bone 1992 SIRS criteria — primary full text is paywalled/bot-blocked; criteria verified
   via an NIH-hosted secondary source. Low risk, but the quote is secondary-sourced.
3. COMPOSER: the 2021 npj paper is retrospective; any "prospective" claim must cite the
   2024 QI deployment study (Boussina) with its quasi-experimental design disclosed.
4. `sources.json` remote_path strings omit subdirectories (verified hashes still match) —
   fix paths to `sepsis/`, `organfailure/`, `score/` before any re-fetch tooling is built.
5. DRAFT §4.1 setA numbers (1,790 positives; 529,958/64,928 emissions) were treated as
   frozen sidecar results and not re-derived in this audit.
