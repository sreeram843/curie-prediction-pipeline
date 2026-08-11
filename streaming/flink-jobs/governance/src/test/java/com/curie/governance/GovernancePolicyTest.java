package com.curie.governance;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class GovernancePolicyTest {

  private static GovernancePolicy.AlertView alert(int score, String tier, String eventTime) {
    GovernancePolicy.AlertView a = new GovernancePolicy.AlertView();
    a.score = score;
    a.tier = tier;
    a.eventTime = eventTime;
    return a;
  }

  @Test
  void suppressesUntilTrajectoryMet() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.trajectoryPersistenceMs = 30 * 60 * 1000L;
    config.minCrossings = 2;
    config.baselineEnabled = false;

    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    assertFalse(
        GovernancePolicy.evaluate(alert(4, "urgent", "2024-01-01T00:00:00Z"), state, config).emit);
    assertFalse(
        GovernancePolicy.evaluate(alert(4, "urgent", "2024-01-01T00:10:00Z"), state, config).emit);
    GovernancePolicy.Decision d3 =
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T00:35:00Z"), state, config);
    assertTrue(d3.emit);
    assertEquals("interruptive", d3.routing);
    assertEquals("governed", d3.alert.governancePath);
  }

  @Test
  void refractoryBlocksDuplicates() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    config.refractoryMs = 120 * 60 * 1000L;

    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    assertTrue(
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T01:00:00Z"), state, config).emit);
    assertEquals(
        "refractory",
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T01:30:00Z"), state, config).reason);
  }

  @Test
  void contextSuppressionHoldsAlert() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    state.contextFlags.add("comfort_care");
    assertTrue(
        GovernancePolicy.evaluate(alert(8, "critical", "2024-01-01T01:00:00Z"), state, config)
            .reason
            .startsWith("context:"));
  }
}
