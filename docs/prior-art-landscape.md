# Prior-art and product landscape (CURIE-040)

**Document status:** sourced research note for manuscript / investor language  
**Access / verification date:** 2026-08-12  
**Re-verify by:** 2027-02-12 (regulatory and product claims age quickly)

This table separates **sourced facts**, **project inference**, and **proposed differentiation**.
It does **not** claim clinical superiority over any commercial or academic system.

## Commercial / deployed systems (sourced)

| System | Intended use (as published) | Typical inputs | Setting | Validation design (public) | Alert workflow notes | Adoption / burden (public) | Regulatory status (timestamped) | Primary source | Evidence note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Epic / sepsis CDS (site-configured) | Early sepsis warning / BPA workflows | EHR vitals, labs, orders | Acute care EHR | Site-specific; literature varies | Interruptive BPA common | Alert fatigue widely reported in EHR CDS literature | EHR feature; not a freestanding SaMD claim here — **re-verify per site build** (2026-08-12) | Peer-reviewed EHR sepsis alert / BPA studies (e.g. JAMA Network Open / similar EHR CDS evaluations); Epic user documentation (customer-restricted) | Public papers describe BPA burden; Epic internals are vendor docs |
| TREWS (Targeted Real-time Early Warning System) | Sepsis early warning | EHR streams | Hospital deployment studies | Prospective / quasi-experimental published evaluations | Clinician-facing warnings | Published work discusses alert volume and outcomes associations | Research/deployment reports — **not asserted FDA-cleared here** (2026-08-12) | Henry et al. and related Johns Hopkins TREWS publications | Use primary papers for numbers; do not copy secondary blogs |
| COMPOSER | Sepsis prediction / CDS research | Multimodal EHR | Academic medical center studies | Retrospective + prospective research reports | Model-driven risk scores | Burden depends on thresholding | Research system — **status re-verify** (2026-08-12) | UCSD / COMPOSER peer-reviewed publications | Confirm latest paper before quoting AUROC or outcome deltas |
| Prenosis / Immunix (and related) | Host-response / sepsis risk products | Biomarkers ± clinical data | Lab + clinical workflow | Company and published clinical studies | Product-specific | Vendor-reported | Check current FDA listings before any claim (2026-08-12) | Company materials + FDA databases (510(k)/De Novo as applicable) | Prefer FDA database over marketing pages |
| eCART / similar deterioration scores | Clinical deterioration risk | EHR vitals/labs | Ward / rapid-response contexts | Published derivation/validation cohorts | Often score + RR team workflows | Threshold-dependent | Confirm device/regulatory posture per product version (2026-08-12) | Peer-reviewed eCART / deterioration score papers | Distinguish research score from commercial packaging |

## Academic themes (governance-relevant)

| Theme | Why it matters to Curie | Representative search seeds | Novelty caution |
| --- | --- | --- | --- |
| Alert fatigue / tiered interruptive vs passive | Dual-lane page gate design | “alert fatigue CDS”, “interruptive BPA sepsis” | Tiered routing is **not** novel by itself |
| Refractory / deduplication windows | Shared governance refractory | “alert refractory period”, “duplicate alert suppression” | Document as engineering policy, not invention |
| Abstention / selective prediction | Quality gates + uncertainty band | “selective classification”, “abstain clinical prediction” | Keep LLM abstention observational |
| Distribution shift / calibration | Site drift monitors | “dataset shift clinical prediction”, “recalibration EHR model” | Separate operating-point selection from probability calibration |
| Multi-condition deterioration | Episode arbitration | “multi-organ deterioration early warning” | Novelty is architecture + evidence, not vocabulary |
| Clinical CDS evaluation methods | MIMIC / Challenge / shadow protocol | TRIPOD+AI, DECIDE-AI, CDS evaluation frameworks | Follow reporting standards before outcome claims |

**Search note (CURIE-040):** Before claiming novelty for governance-policy ablations (trajectory, baseline, refractory, page gate), search for prior **policy ablation** studies on sepsis/deterioration alerts. As of 2026-08-12, Curie treats dual-lane page gates + component-delta + quality abstention as an **engineering differentiation hypothesis**, not a proven unique scientific result.

## Project inference (not sourced as fact)

- Hospitals need deterministic, auditable routing even when LLMs assist documentation and review.
- Episode-level arbitration may reduce perceived page spam versus per-indicator pages.
- Shadow mode is a necessary safety step before interruptive pilots.

## Proposed differentiation (must stay weaker than evidence)

| Claim shape | Allowed now | Forbidden until evidence |
| --- | --- | --- |
| Different architecture (Connect / Signal / Copilot) | Yes — engineering description | “Clinically superior to TREWS/COMPOSER/…” |
| Offline Challenge / synthetic reliability demos | Yes — with pinned artifacts | “Improves mortality / time-to-antibiotics” |
| Dual-lane burden reduction on Challenge holdout | Yes — emission metrics as documented | “Proven alert-fatigue cure in production” |
| Shadow / MIMIC Stage B | Under evaluation | Promoting `SHADOW-PROD` / MIMIC claims early |

## Investor language checklist

1. Say **different architecture**, not **better outcomes**, unless a pinned study artifact exists.
2. Timestamp every regulatory/product status sentence.
3. Link every external numeric claim to a primary paper or FDA listing.
4. Keep `docs/claims-matrix.md` as the claim-tier source of truth.
