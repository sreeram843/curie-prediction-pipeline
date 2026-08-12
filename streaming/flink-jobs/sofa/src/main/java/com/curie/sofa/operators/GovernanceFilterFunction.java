package com.curie.sofa.operators;

import com.curie.governance.GovernancePolicy;
import com.curie.sofa.model.AlertEvent;
import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.model.RuleVersions;
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
 * Copies routing / page-defer metadata onto emitted alerts.
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
    view.positiveComponents =
        value.positive_components != null
            ? value.positive_components
            : countPositiveComponents(value);
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
      value.routing = decision.routing;
      value.page_deferred_reason = decision.alert.pageDeferredReason;
      if (value.positive_components == null) {
        value.positive_components = view.positiveComponents;
      }
      out.collect(value);
    }
  }

  static int countPositiveComponents(AlertEvent value) {
    if (value == null || value.component_breakdown == null) {
      return 0;
    }
    int n = 0;
    for (AlertEvent.ComponentBreakdown c : value.component_breakdown) {
      if (c != null && !c.missing && c.points != null && c.points > 0) {
        n++;
      }
    }
    return n;
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
    int resolutionGap = g.dedup != null ? g.dedup.resolution_gap_minutes : 60;
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
    boolean pageGate = g.page_gate != null && g.page_gate.enabled;
    int pageCrossings = g.page_gate != null ? g.page_gate.min_crossings : 2;
    int pagePersist =
        g.page_gate != null ? g.page_gate.trajectory_persistence_minutes : 30;
    int pageDelta = g.page_gate != null ? g.page_gate.min_score_delta : 1;
    int pagePos = g.page_gate != null ? g.page_gate.min_positive_components : 0;
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
        passive,
        pageGate,
        pageCrossings,
        pagePersist,
        pageDelta,
        pagePos);
  }
}
