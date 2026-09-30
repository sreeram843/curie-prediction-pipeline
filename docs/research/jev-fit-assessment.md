# Jev fit assessment

Date: 2026-09-21. Proposal only; no runtime integration or clinical validation.

## Capability and boundary

TypeSafe documents Jev as a typed decision model, with Choice, Score and Noul
primitives rather than free-text generation. Choice and Score return probability
distributions and confidence. This fits bounded classification and semantic review;
it does not directly replace the GRP narrative generator.
[Source: official introduction](https://docs.typesafe.ai/introduction).

The launch article claims schema guarantees and substantial speed/cost gains. Those
claims do not establish clinical correctness or calibration on Curie's data; its
workflow comparisons use other models' reference probabilities. A schema-valid
answer can still be factually wrong.
[Source: launch article](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

The existing [off-alert-path decision](../adr/0002-llm-off-alert-path.md) remains
binding regardless of whether the vendor calls Jev an LLM or a System One model.
No model decision may change scoring, suppression, severity, routing or thresholds.

## Candidate uses, in recommended experiment order

1. **Feedback classification:** compare Jev against the keyword classifier in
   `eval/stewardship/classifier.py`, using the existing taxonomy and independent
   reviewer labels. Example: “The team had already addressed this before the page”
   may map to `already_treated`, or abstain when ambiguous. This is offline analytics,
   not permission to suppress an alert or activate a rule.
2. **Narrative semantic review:** supplement `reasoning/claim_validator.py`, which
   checks forbidden phrases and evidence-ID membership but does not establish
   semantic entailment. Classify each claim as supported, contradicted or insufficient
   evidence against an immutable evidence snapshot. Include the summary, which
   `reasoning/policy_gate.py` currently appends separately from validated claims.
   Missing source facts must yield insufficient evidence. Initially record judgments
   in shadow mode; any eventual quarantine applies only to narrative text.
3. **Candidate extraction review:** label proposed spans for negation, temporality,
   experiencer and uncertainty alongside `ingestion/extraction/`. Keep exact spans,
   numeric values and provenance under deterministic validation. Jev should select
   from supplied candidates rather than invent source spans or arbitrary FHIR JSON.
   Outputs remain untrusted candidates, outside alert inputs.

## Smallest useful experiment

Start with feedback classification on synthetic text. Keep the keyword baseline;
compare both against held-out, independently reviewed examples, including paraphrases,
ambiguous and multi-reason feedback, empty input and injection attempts. Measure
per-category precision/recall, macro F1, accuracy at different abstention coverage,
calibration, latency and cost. Do not treat model confidence as clinical probability.

Keep model and prompt versions, explicit abstention, an off-by-default flag and a
kill switch. Test unavailable-service and timeout behavior. No changes to Flink,
rule bundles, governance, frozen studies or existing feature-flag defaults are needed
for an offline experiment. Proceed only if measured improvement warrants integration.

## Supporting official documentation

- [Citation checking](https://docs.typesafe.ai/cookbooks/citation_check) describes
  classifying whether a source supports a claim.
- [Pre-parsed extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook)
  describes selecting candidates found by code.
- [Confidence](https://docs.typesafe.ai/confidence) explains distribution-derived
  confidence and application-specific threshold evaluation.
- [Jev 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) notes
  numeric precision, counting, date-comparison and adversarial-input limitations.
  Arithmetic and temporal criteria must remain deterministic.
