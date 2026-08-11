package com.curie.sofa.operators;

import com.curie.sofa.fhir.FhirSofaMapper;
import com.curie.sofa.model.AlertEvent;
import com.curie.sofa.model.CanonicalEvent;
import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.scoring.SofaScorer;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.curie.sofa.scoring.SofaScorer.ScoreResult;
import com.curie.sofa.scoring.SofaScorer.Tier;
import com.curie.sofa.state.PatientSofaState;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.apache.flink.api.common.state.MapStateDescriptor;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.co.KeyedBroadcastProcessFunction;
import org.apache.flink.util.Collector;

/**
 * Keyed by patient_id. Clinical events update SOFA feature state; rule broadcasts refresh
 * thresholds. Emits a naive alert when score >= threshold and data is scoreable.
 */
public class SofaAlertFunction
    extends KeyedBroadcastProcessFunction<String, CanonicalEvent, RuleBundle, AlertEvent> {

  public static final MapStateDescriptor<String, RuleBundle> RULE_STATE_DESC =
      new MapStateDescriptor<>(
          "sofa-rules", TypeInformation.of(String.class), TypeInformation.of(RuleBundle.class));

  private transient ValueState<PatientSofaState> patientState;

  @Override
  public void open(Configuration parameters) {
    patientState =
        getRuntimeContext()
            .getState(new ValueStateDescriptor<>("patient-sofa", PatientSofaState.class));
  }

  @Override
  public void processBroadcastElement(RuleBundle value, Context ctx, Collector<AlertEvent> out)
      throws Exception {
    if (value == null || value.bundle_id == null) {
      return;
    }
    ctx.getBroadcastState(RULE_STATE_DESC).put(value.bundle_id, value);
  }

  @Override
  public void processElement(CanonicalEvent event, ReadOnlyContext ctx, Collector<AlertEvent> out)
      throws Exception {
    if (event == null || event.patient_id == null || event.resource == null) {
      return;
    }
    List<ComponentInput> updates = FhirSofaMapper.extract(event.resource);
    if (updates.isEmpty()) {
      return;
    }

    PatientSofaState state = patientState.value();
    if (state == null) {
      state = new PatientSofaState();
      state.patientId = event.patient_id;
    }
    if (event.encounter_id != null) {
      state.encounterId = event.encounter_id;
    }
    for (ComponentInput u : updates) {
      state.apply(u);
    }
    patientState.update(state);

    RuleBundle rules = ctx.getBroadcastState(RULE_STATE_DESC).get("sepsis-sofa");
    if (rules == null) {
      rules = RuleBundle.defaults();
    }

    long eventTimeMs = parseTimeMs(event.event_time);
    int minComponents =
        rules.score != null && rules.score.min_components_required > 0
            ? rules.score.min_components_required
            : 3;
    ScoreResult score =
        SofaScorer.compute(
            state.patientId,
            state.encounterId,
            eventTimeMs,
            state.snapshotInputs(),
            rules.bundle_id,
            rules.version,
            minComponents);

    if (score.completeness == SofaScorer.Completeness.INSUFFICIENT_DATA) {
      return;
    }
    int threshold = rules.alert != null ? rules.alert.naive_threshold : 2;
    Tier tier = SofaScorer.tierForScore(score.totalScore, threshold);
    if (tier == Tier.NONE) {
      return;
    }

    String ingestIso =
        event.ingest_time != null ? event.ingest_time : Instant.ofEpochMilli(eventTimeMs).toString();
    String alertId =
        "alert-"
            + UUID.nameUUIDFromBytes(
                    (event.patient_id
                            + "|"
                            + score.totalScore
                            + "|"
                            + eventTimeMs
                            + "|"
                            + rules.version)
                        .getBytes())
                .toString();
    out.collect(AlertEvent.fromScore(score, tier, alertId, ingestIso));
  }

  public static long parseTimeMs(String iso) {
    if (iso == null || iso.isBlank()) {
      return Instant.EPOCH.toEpochMilli();
    }
    return Instant.parse(iso.replace(" ", "T")).toEpochMilli();
  }
}
