package com.curie.sofa.aki;

import com.curie.sofa.model.AlertEvent;
import com.curie.sofa.model.AlertIds;
import com.curie.sofa.model.CanonicalEvent;
import com.curie.sofa.model.DlqEvent;
import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.model.RuleVersions;
import com.curie.sofa.operators.SofaAlertFunction;
import com.curie.sofa.state.IdempotencyCache;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Locale;
import java.util.Set;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.co.KeyedBroadcastProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;

/**
 * Kafka clinical events → AKI score → naive alerts (including below-threshold recovery). Shared
 * governance runs downstream.
 *
 * <p>Creatinine: LOINC 2160-0 (mg/dL). Urine: LOINC 9187-6 with unit {@code mL/kg/h} plus component
 * {@code duration-hours}; anuria via code {@code anuria} / Curie {@code urine-anuria}.
 */
public class AkiAlertFunction
    extends KeyedBroadcastProcessFunction<String, CanonicalEvent, RuleBundle, AlertEvent> {

  public static final OutputTag<DlqEvent> DLQ_TAG = new OutputTag<>("aki-dlq") {};

  public static final String LOINC_CREATININE = "2160-0";
  /** Urine output rate observation (value = mL/kg/h). */
  public static final String LOINC_URINE_OUTPUT = "9187-6";
  public static final String CODE_ANURIA = "anuria";
  public static final String CURIE_ANURIA = "urine-anuria";
  public static final String COMPONENT_DURATION_HOURS = "duration-hours";

  private static final Set<String> USABLE_STATUS =
      Set.of("final", "amended", "corrected", "preliminary");

  private transient ValueState<PatientAkiState> patientState;
  private transient ValueState<IdempotencyCache> idempotency;

  @Override
  public void open(Configuration parameters) {
    patientState =
        getRuntimeContext()
            .getState(new ValueStateDescriptor<>("patient-aki", PatientAkiState.class));
    idempotency =
        getRuntimeContext()
            .getState(new ValueStateDescriptor<>("aki-idempotency-cache", IdempotencyCache.class));
  }

  @Override
  public void processBroadcastElement(RuleBundle value, Context ctx, Collector<AlertEvent> out)
      throws Exception {
    if (value == null || value.bundle_id == null) {
      return;
    }
    RuleBundle current =
        ctx.getBroadcastState(SofaAlertFunction.RULE_STATE_DESC).get(value.bundle_id);
    if (current != null
        && current.version != null
        && value.version != null
        && RuleVersions.compare(value.version, current.version) < 0) {
      return;
    }
    ctx.getBroadcastState(SofaAlertFunction.RULE_STATE_DESC).put(value.bundle_id, value);
  }

  @Override
  public void processElement(CanonicalEvent event, ReadOnlyContext ctx, Collector<AlertEvent> out)
      throws Exception {
    if (event == null) {
      return;
    }
    if (event.parse_error != null && !event.parse_error.isBlank()) {
      emitDlq(ctx, event, "malformed_json:" + event.parse_error, null, null, null);
      return;
    }
    if (event.patient_id == null || event.resource == null) {
      return;
    }

    Long eventTimeMsObj = SofaAlertFunction.tryParseTimeMs(event.event_time);
    if (eventTimeMsObj == null) {
      emitDlq(ctx, event, "invalid_timestamp", null, null, null);
      return;
    }
    long eventTimeMs = eventTimeMsObj;
    long ingestTimeMs = eventTimeMs;
    if (event.ingest_time != null && !event.ingest_time.isBlank()) {
      Long ingest = SofaAlertFunction.tryParseTimeMs(event.ingest_time);
      if (ingest == null) {
        emitDlq(ctx, event, "invalid_ingest_timestamp", null, null, null);
        return;
      }
      ingestTimeMs = ingest;
    }

    IdempotencyCache cache = idempotency.value();
    if (cache == null) {
      cache = new IdempotencyCache();
    }
    if (cache.seen(event.idempotency_key, ingestTimeMs)) {
      idempotency.update(cache);
      return;
    }
    idempotency.update(cache);

    JsonNode resource = event.resource;
    if (!"Observation".equals(text(resource, "resourceType"))) {
      return;
    }

    String status = text(resource, "status");
    if (status != null && !USABLE_STATUS.contains(status.toLowerCase(Locale.ROOT))) {
      emitDlq(ctx, event, "invalid_status:" + status, null, null, status);
      return;
    }

    String code = primaryCode(resource);
    if (code == null) {
      return;
    }

    PatientAkiState state = patientState.value();
    if (state == null) {
      state = new PatientAkiState();
      state.patientId = event.patient_id;
    }
    if (event.encounter_id != null
        && !event.encounter_id.isBlank()
        && state.encounterId != null
        && !event.encounter_id.equals(state.encounterId)) {
      state.resetForEncounter(event.encounter_id);
    } else if (event.encounter_id != null) {
      state.encounterId = event.encounter_id;
    }

    String evidenceId = evidenceId(resource);
    boolean applied;
    if (LOINC_CREATININE.equals(code)) {
      applied = applyCreatinine(ctx, event, state, resource, code, status, eventTimeMs, evidenceId);
    } else if (LOINC_URINE_OUTPUT.equals(code)) {
      applied = applyUrineRate(ctx, event, state, resource, code, status, eventTimeMs, evidenceId);
    } else if (CODE_ANURIA.equalsIgnoreCase(code) || CURIE_ANURIA.equalsIgnoreCase(code)) {
      applied = applyAnuria(state, resource, eventTimeMs, evidenceId);
    } else {
      return;
    }
    patientState.update(state);
    if (!applied) {
      return;
    }

    RuleBundle rules = ctx.getBroadcastState(SofaAlertFunction.RULE_STATE_DESC).get("aki-kdigo");
    if (rules == null) {
      rules = akiDefaults();
    }
    int threshold = rules.alert != null ? rules.alert.naive_threshold : 2;
    AkiScorer.Result score =
        AkiScorer.compute(
            state.patientId,
            state.encounterId,
            eventTimeMs,
            state.toInput(),
            rules.version);
    if ("insufficient_data".equals(score.completeness) || score.totalScore == null) {
      return;
    }
    String tier = AkiScorer.tierForScore(score.totalScore, threshold);

    String ingest =
        event.ingest_time != null
            ? event.ingest_time
            : Instant.ofEpochMilli(eventTimeMs).toString();
    String alertId =
        AlertIds.of(
            event.patient_id,
            state.encounterId,
            "aki",
            score.totalScore,
            eventTimeMs,
            rules.version);
    AlertEvent alert = AlertEvent.fromAki(score, tier, alertId, ingest);
    alert.rule_bundle_id = rules.bundle_id;
    alert.rule_version = rules.version;
    alert.rule_bundle_hash = rules.content_hash;
    if (event.context_flags != null) {
      alert.context_flags = new ArrayList<>(event.context_flags);
    }
    out.collect(alert);
  }

  private boolean applyCreatinine(
      ReadOnlyContext ctx,
      CanonicalEvent event,
      PatientAkiState state,
      JsonNode resource,
      String code,
      String status,
      long eventTimeMs,
      String evidenceId) {
    Double value = numericValue(resource);
    String unit = unit(resource);
    if (value == null) {
      emitDlq(ctx, event, "missing_value", code, unit, status);
      return false;
    }
    if (unit == null
        || !(unit.equalsIgnoreCase("mg/dL") || unit.equalsIgnoreCase("mg/dl"))) {
      emitDlq(ctx, event, "invalid_unit", code, unit, status);
      return false;
    }
    boolean asBaseline =
        resource.has("interpretation")
            && resource.path("interpretation").toString().toLowerCase(Locale.ROOT).contains("baseline");
    return state.applyCreatinine(value, eventTimeMs, evidenceId, asBaseline);
  }

  private boolean applyUrineRate(
      ReadOnlyContext ctx,
      CanonicalEvent event,
      PatientAkiState state,
      JsonNode resource,
      String code,
      String status,
      long eventTimeMs,
      String evidenceId) {
    Double rate = numericValue(resource);
    String unit = unit(resource);
    if (rate == null) {
      emitDlq(ctx, event, "missing_value", code, unit, status);
      return false;
    }
    if (unit == null
        || !(unit.equalsIgnoreCase("mL/kg/h")
            || unit.equalsIgnoreCase("ml/kg/h")
            || unit.equalsIgnoreCase("mL/kg/hr"))) {
      emitDlq(ctx, event, "invalid_unit", code, unit, status);
      return false;
    }
    Double durationHours = componentNumeric(resource, COMPONENT_DURATION_HOURS);
    Boolean anuria = componentBoolean(resource, CODE_ANURIA);
    if (anuria == null) {
      anuria = componentBoolean(resource, CURIE_ANURIA);
    }
    return state.applyUrine(rate, durationHours, anuria, eventTimeMs, evidenceId);
  }

  private boolean applyAnuria(
      PatientAkiState state, JsonNode resource, long eventTimeMs, String evidenceId) {
    Boolean anuria = booleanValue(resource);
    if (anuria == null) {
      anuria = true;
    }
    Double durationHours = componentNumeric(resource, COMPONENT_DURATION_HOURS);
    if (durationHours == null) {
      durationHours = numericValue(resource);
    }
    return state.applyUrine(null, durationHours, anuria, eventTimeMs, evidenceId);
  }

  private static RuleBundle akiDefaults() {
    RuleBundle b = new RuleBundle();
    b.bundle_id = "aki-kdigo";
    b.version = "0.2.0";
    b.indicator = "aki";
    b.alert.naive_threshold = 2;
    return b;
  }

  private void emitDlq(
      ReadOnlyContext ctx,
      CanonicalEvent event,
      String reason,
      String code,
      String unit,
      String status) {
    DlqEvent dlq = new DlqEvent();
    dlq.patient_id = event.patient_id;
    dlq.encounter_id = event.encounter_id;
    dlq.event_time = event.event_time;
    dlq.ingest_time = event.ingest_time;
    dlq.idempotency_key = event.idempotency_key;
    dlq.reason = reason;
    dlq.code = code;
    dlq.unit = unit;
    dlq.status = status;
    dlq.resource_type = "Observation";
    dlq.source = "aki-fhir-mapper";
    ctx.output(DLQ_TAG, dlq);
  }

  private static String primaryCode(JsonNode resource) {
    JsonNode coding = resource.path("code").path("coding");
    if (!coding.isArray()) {
      return null;
    }
    for (JsonNode c : coding) {
      if (c.has("code")) {
        return c.get("code").asText();
      }
    }
    return null;
  }

  private static Double numericValue(JsonNode resource) {
    JsonNode qty = resource.get("valueQuantity");
    if (qty != null && qty.has("value") && qty.get("value").isNumber()) {
      return qty.get("value").asDouble();
    }
    return null;
  }

  private static Boolean booleanValue(JsonNode resource) {
    if (resource.has("valueBoolean")) {
      return resource.get("valueBoolean").asBoolean();
    }
    return null;
  }

  private static Double componentNumeric(JsonNode resource, String code) {
    JsonNode components = resource.get("component");
    if (components == null || !components.isArray()) {
      return null;
    }
    for (JsonNode c : components) {
      String cCode = primaryCode(c);
      if (code.equalsIgnoreCase(cCode)) {
        return numericValue(c);
      }
    }
    return null;
  }

  private static Boolean componentBoolean(JsonNode resource, String code) {
    JsonNode components = resource.get("component");
    if (components == null || !components.isArray()) {
      return null;
    }
    for (JsonNode c : components) {
      String cCode = primaryCode(c);
      if (code.equalsIgnoreCase(cCode)) {
        return booleanValue(c);
      }
    }
    return null;
  }

  private static String unit(JsonNode resource) {
    JsonNode qty = resource.get("valueQuantity");
    if (qty == null) {
      return null;
    }
    if (qty.has("unit")) {
      return qty.get("unit").asText();
    }
    if (qty.has("code")) {
      return qty.get("code").asText();
    }
    return null;
  }

  private static String evidenceId(JsonNode resource) {
    String type = text(resource, "resourceType");
    String id = text(resource, "id");
    if (type != null && id != null) {
      return type + "/" + id;
    }
    return null;
  }

  private static String text(JsonNode node, String field) {
    if (node == null || !node.has(field) || node.get(field).isNull()) {
      return null;
    }
    return node.get(field).asText();
  }
}
