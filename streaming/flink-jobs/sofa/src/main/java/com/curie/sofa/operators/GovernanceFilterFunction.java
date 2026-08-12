package com.curie.sofa.operators;

import com.curie.governance.GovernancePolicy;
import com.curie.sofa.model.AlertEvent;
import com.curie.sofa.model.RuleBundle;
import java.util.HashSet;
import java.util.Set;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.co.KeyedBroadcastProcessFunction;
import org.apache.flink.util.Collector;

/**
 * Applies shared governance policy to naive alerts using the broadcast rule bundle's governance
 * knobs. Handles below-threshold recovery signals (tier {@code none}) and context_flags.
 */
public class GovernanceFilterFunction
    extends KeyedBroadcastProcessFunction<String, AlertEvent, RuleBundle, AlertEvent> {

  private transient ValueState<GovernancePolicy.PatientGovState> govState;

  @Override
  public void open(Configuration parameters) {
    govState =
        getRuntimeContext()
            .getState(
                new ValueStateDescriptor<>("patient-gov", GovernancePolicy.PatientGovState.class));
  }

  @Override
  public void processBroadcastElement(RuleBundle value, Context ctx, Collector<AlertEvent> out)
      throws Exception {
    if (value == null || value.bundle_id == null) {
      return;
    }
    ctx.getBroadcastState(SofaAlertFunction.RULE_STATE_DESC).put(value.bundle_id, value);
  }

  @Override
  public void processElement(AlertEvent value, ReadOnlyContext ctx, Collector<AlertEvent> out)
      throws Exception {
    GovernancePolicy.PatientGovState state = govState.value();
    if (state == null) {
      state = new GovernancePolicy.PatientGovState();
    }
    GovernancePolicy.AlertView view = new GovernancePolicy.AlertView();
    view.score = value.score;
    view.tier = value.tier;
    view.eventTime = value.event_time;
    view.encounterId = value.encounter_id;
    view.governancePath = value.governance_path;
    view.suppressed = value.suppressed;
    view.suppressionReason = value.suppression_reason;
    if (value.context_flags != null) {
      view.contextFlags.addAll(value.context_flags);
    }

    String bundleId = value.rule_bundle_id != null ? value.rule_bundle_id : "sepsis-sofa";
    RuleBundle rules = ctx.getBroadcastState(SofaAlertFunction.RULE_STATE_DESC).get(bundleId);
    GovernancePolicy.Config config = configFromBundle(rules);

    GovernancePolicy.Decision decision = GovernancePolicy.evaluate(view, state, config);
    govState.update(state);
    if (decision.emit) {
      value.governance_path = decision.alert.governancePath;
      value.suppressed = decision.alert.suppressed;
      value.suppression_reason = decision.alert.suppressionReason;
      out.collect(value);
    }
  }

  static GovernancePolicy.Config configFromBundle(RuleBundle rules) {
    if (rules == null || rules.governance == null) {
      return new GovernancePolicy.Config();
    }
    RuleBundle.GovernanceConfig g = rules.governance;
    int persistence = g.trajectory != null ? g.trajectory.min_persistence_minutes : 30;
    int crossings = g.trajectory != null ? g.trajectory.min_crossings : 2;
    boolean baseline = g.baseline == null || g.baseline.enabled;
    int delta = g.baseline != null ? g.baseline.delta_threshold : 2;
    int lookback = g.baseline != null ? g.baseline.lookback_hours : 24;
    int refractory = g.dedup != null ? g.dedup.refractory_minutes : 120;
    int resolutionGap = 60;
    Set<String> flags = new HashSet<>();
    if (g.suppression != null && g.suppression.flags != null) {
      flags.addAll(g.suppression.flags);
    }
    Set<String> interruptive = new HashSet<>();
    Set<String> passive = new HashSet<>();
    if (g.tiering != null) {
      if (g.tiering.interruptive_tiers != null) {
        interruptive.addAll(g.tiering.interruptive_tiers);
      }
      if (g.tiering.passive_tiers != null) {
        passive.addAll(g.tiering.passive_tiers);
      }
    }
    return GovernancePolicy.Config.fromBundleKnobs(
        persistence,
        crossings,
        baseline,
        delta,
        lookback,
        refractory,
        resolutionGap,
        flags,
        interruptive,
        passive);
  }
}
