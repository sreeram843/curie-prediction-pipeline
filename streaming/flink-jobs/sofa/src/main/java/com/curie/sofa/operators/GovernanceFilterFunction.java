package com.curie.sofa.operators;

import com.curie.governance.GovernancePolicy;
import com.curie.sofa.model.AlertEvent;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

/** Applies shared governance policy to naive SOFA alerts; drops suppressed ones. */
public class GovernanceFilterFunction extends KeyedProcessFunction<String, AlertEvent, AlertEvent> {

  private transient ValueState<GovernancePolicy.PatientGovState> govState;

  @Override
  public void open(Configuration parameters) {
    govState =
        getRuntimeContext()
            .getState(
                new ValueStateDescriptor<>("patient-gov", GovernancePolicy.PatientGovState.class));
  }

  @Override
  public void processElement(AlertEvent value, Context ctx, Collector<AlertEvent> out)
      throws Exception {
    GovernancePolicy.PatientGovState state = govState.value();
    if (state == null) {
      state = new GovernancePolicy.PatientGovState();
    }
    GovernancePolicy.AlertView view = new GovernancePolicy.AlertView();
    view.score = value.score;
    view.tier = value.tier;
    view.eventTime = value.event_time;
    view.governancePath = value.governance_path;
    view.suppressed = value.suppressed;
    view.suppressionReason = value.suppression_reason;

    GovernancePolicy.Decision decision =
        GovernancePolicy.evaluate(view, state, new GovernancePolicy.Config());
    govState.update(state);
    if (decision.emit) {
      value.governance_path = decision.alert.governancePath;
      value.suppressed = decision.alert.suppressed;
      value.suppression_reason = decision.alert.suppressionReason;
      out.collect(value);
    }
  }
}
