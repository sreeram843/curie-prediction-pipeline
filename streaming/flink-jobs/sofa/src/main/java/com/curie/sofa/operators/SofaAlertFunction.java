package com.curie.sofa.operators;

import com.curie.sofa.fhir.FhirSofaMapper;
import com.curie.sofa.fhir.FhirSofaMapper.ExtractResult;
import com.curie.sofa.fhir.FhirSofaMapper.InvalidEvent;
import com.curie.sofa.model.AlertEvent;
import com.curie.sofa.model.AlertIds;
import com.curie.sofa.model.CanonicalEvent;
import com.curie.sofa.model.DlqEvent;
import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.model.RuleVersions;
import com.curie.sofa.scoring.SofaScorer;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.curie.sofa.scoring.SofaScorer.ScoreResult;
import com.curie.sofa.scoring.SofaScorer.Tier;
import com.curie.sofa.scoring.SofaThresholds;
import com.curie.sofa.state.EventTimeBuffer;
import com.curie.sofa.state.IdempotencyCache;
import com.curie.sofa.state.PatientSofaState;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.apache.flink.api.common.state.MapStateDescriptor;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.co.KeyedBroadcastProcessFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;

/**
 * Keyed by patient_id. Clinical events are reordered through a checkpointed {@link
 * EventTimeBuffer} before feature mutation and scoring (CURIE-006 / CURIE-026). Deduplicates by
 * idempotency_key. Emits naive alerts including below-threshold recovery signals (tier {@code
 * none}) so governance can reset trajectory.
 *
 * <p>Event-time timers at {@code eventTime + allowedLateness} flush the final event for a key
 * without requiring a following arrival.
 */
public class SofaAlertFunction
    extends KeyedBroadcastProcessFunction<String, CanonicalEvent, RuleBundle, AlertEvent> {

  public static final MapStateDescriptor<String, RuleBundle> RULE_STATE_DESC =
      new MapStateDescriptor<>(
          "sofa-rules", TypeInformation.of(String.class), TypeInformation.of(RuleBundle.class));

  public static final OutputTag<DlqEvent> DLQ_TAG = new OutputTag<>("dlq") {};

  /** Matches SofaJob bounded out-of-orderness (5 minutes). */
  public static final long DEFAULT_ALLOWED_LATENESS_MS = 5L * 60L * 1000L;

  public static final String EVENT_TIME_POLICY_VERSION = EventTimeBuffer.POLICY_VERSION;

  private transient ValueState<PatientSofaState> patientState;
  private transient ValueState<IdempotencyCache> idempotency;
  private transient ValueState<EventTimeBuffer<CanonicalEvent>> eventBuffer;

  @Override
  public void open(Configuration parameters) {
    patientState =
        getRuntimeContext()
            .getState(new ValueStateDescriptor<>("patient-sofa", PatientSofaState.class));
    idempotency =
        getRuntimeContext()
            .getState(new ValueStateDescriptor<>("idempotency-cache", IdempotencyCache.class));
    @SuppressWarnings({"unchecked", "rawtypes"})
    ValueStateDescriptor<EventTimeBuffer<CanonicalEvent>> bufDesc =
        new ValueStateDescriptor("event-time-buffer", EventTimeBuffer.class);
    eventBuffer = getRuntimeContext().getState(bufDesc);
  }

  @Override
  public void processBroadcastElement(RuleBundle value, Context ctx, Collector<AlertEvent> out)
      throws Exception {
    if (value == null || value.bundle_id == null) {
      return;
    }
    RuleBundle current = ctx.getBroadcastState(RULE_STATE_DESC).get(value.bundle_id);
    if (current != null
        && current.version != null
        && value.version != null
        && RuleVersions.compare(value.version, current.version) < 0) {
      // Reject silent rollback: older broadcasts cannot replace a newer active version.
      return;
    }
    ctx.getBroadcastState(RULE_STATE_DESC).put(value.bundle_id, value);
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

    Long eventTimeMsObj = tryParseTimeMs(event.event_time);
    if (eventTimeMsObj == null) {
      emitDlq(ctx, event, "invalid_timestamp", null, null, null);
      return;
    }
    long eventTimeMs = eventTimeMsObj;
    long ingestTimeMs = eventTimeMs;
    if (event.ingest_time != null && !event.ingest_time.isBlank()) {
      Long ingest = tryParseTimeMs(event.ingest_time);
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

    EventTimeBuffer<CanonicalEvent> buffer = eventBuffer.value();
    if (buffer == null) {
      buffer = new EventTimeBuffer<>(DEFAULT_ALLOWED_LATENESS_MS);
    }
    String tie =
        event.idempotency_key != null && !event.idempotency_key.isBlank()
            ? event.idempotency_key
            : "";
    EventTimeBuffer.FlushResult<CanonicalEvent> flush = buffer.offer(eventTimeMs, event, tie);
    // Timer advances watermark so a lone final event still flushes (CURIE-026).
    ctx.timerService().registerEventTimeTimer(buffer.flushTimerTimestamp(eventTimeMs));
    eventBuffer.update(buffer);

    applyFlush(flush, ctx, out);
  }

  @Override
  public void onTimer(long timestamp, OnTimerContext ctx, Collector<AlertEvent> out)
      throws Exception {
    EventTimeBuffer<CanonicalEvent> buffer = eventBuffer.value();
    if (buffer == null) {
      return;
    }
    EventTimeBuffer.FlushResult<CanonicalEvent> flush = buffer.advanceWatermark(timestamp);
    eventBuffer.update(buffer);
    applyFlush(flush, ctx, out);
  }

  private void applyFlush(
      EventTimeBuffer.FlushResult<CanonicalEvent> flush,
      ReadOnlyContext ctx,
      Collector<AlertEvent> out)
      throws Exception {
    for (EventTimeBuffer.BufferedEvent<CanonicalEvent> late : flush.late) {
      emitDlq(ctx, late.payload, EventTimeBuffer.LATE_DISPOSITION, null, null, null);
    }
    for (EventTimeBuffer.BufferedEvent<CanonicalEvent> ready : flush.ready) {
      scoreReadyEvent(ready.payload, ready.eventTimeMs, ctx, out);
    }
  }

  private void scoreReadyEvent(
      CanonicalEvent event, long eventTimeMs, ReadOnlyContext ctx, Collector<AlertEvent> out)
      throws Exception {
    long ingestTimeMs = eventTimeMs;
    if (event.ingest_time != null && !event.ingest_time.isBlank()) {
      Long ingest = tryParseTimeMs(event.ingest_time);
      if (ingest != null) {
        ingestTimeMs = ingest;
      }
    }

    ExtractResult extracted = FhirSofaMapper.extractValidated(event.resource);
    for (InvalidEvent inv : extracted.invalid) {
      DlqEvent dlq = new DlqEvent();
      dlq.patient_id = event.patient_id;
      dlq.encounter_id = event.encounter_id;
      dlq.event_time = event.event_time;
      dlq.ingest_time = event.ingest_time;
      dlq.idempotency_key = event.idempotency_key;
      dlq.reason = inv.reason;
      dlq.resource_type = inv.resourceType;
      dlq.resource_id = inv.resourceId;
      dlq.code = inv.code;
      dlq.unit = inv.unit;
      dlq.status = inv.status;
      ctx.output(DLQ_TAG, dlq);
    }
    List<ComponentInput> updates = extracted.inputs;
    if (updates.isEmpty()) {
      return;
    }

    PatientSofaState state = patientState.value();
    if (state == null) {
      state = new PatientSofaState();
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

    boolean anyApplied = false;
    for (ComponentInput u : updates) {
      if (state.apply(u, eventTimeMs, ingestTimeMs)) {
        anyApplied = true;
      }
    }
    patientState.update(state);
    if (!anyApplied) {
      return;
    }

    RuleBundle rules = ctx.getBroadcastState(RULE_STATE_DESC).get("sepsis-sofa");
    if (rules == null) {
      rules = RuleBundle.defaults();
    }

    int minComponents =
        rules.score != null && rules.score.min_components_required > 0
            ? rules.score.min_components_required
            : 3;
    SofaThresholds thresholds = SofaThresholds.fromBundle(rules);
    ScoreResult score =
        SofaScorer.compute(
            state.patientId,
            state.encounterId,
            eventTimeMs,
            state.snapshotInputs(),
            rules.bundle_id,
            rules.version,
            minComponents,
            thresholds);

    if (score.completeness == SofaScorer.Completeness.INSUFFICIENT_DATA) {
      return;
    }
    int threshold = rules.alert != null ? rules.alert.naive_threshold : 2;
    List<RuleBundle.SeverityBand> bands =
        rules.alert != null ? rules.alert.severity_bands : null;
    Tier tier = SofaScorer.tierForScore(score.totalScore, threshold, bands);

    String ingestIso =
        event.ingest_time != null ? event.ingest_time : Instant.ofEpochMilli(eventTimeMs).toString();
    String indicator =
        rules.indicator != null && !rules.indicator.isBlank()
            ? rules.indicator
            : "sofa-deterioration";
    String alertId =
        AlertIds.of(
            event.patient_id,
            state.encounterId,
            indicator,
            score.totalScore,
            eventTimeMs,
            rules.version);
    AlertEvent alert = AlertEvent.fromScore(score, tier, alertId, ingestIso);
    alert.indicator = indicator;
    alert.rule_bundle_id = rules.bundle_id;
    alert.rule_version = rules.version;
    alert.rule_bundle_hash = rules.content_hash;
    if (event.context_flags != null) {
      alert.context_flags = new ArrayList<>(event.context_flags);
    }
    // Always forward to governance — including tier=none for recovery reset.
    out.collect(alert);
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
    dlq.source = "sofa-alert-function";
    ctx.output(DLQ_TAG, dlq);
  }

  /** @return epoch millis, or null if unparseable */
  public static Long tryParseTimeMs(String iso) {
    if (iso == null || iso.isBlank()) {
      return Instant.EPOCH.toEpochMilli();
    }
    try {
      return Instant.parse(iso.replace(" ", "T")).toEpochMilli();
    } catch (Exception e) {
      return null;
    }
  }

  /** @deprecated prefer {@link #tryParseTimeMs}; blank → epoch, invalid → throws */
  public static long parseTimeMs(String iso) {
    Long ms = tryParseTimeMs(iso);
    if (ms == null) {
      throw new IllegalArgumentException("invalid timestamp: " + iso);
    }
    return ms;
  }
}
