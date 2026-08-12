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

  @Test
  void contextFlagsOnAlertSuppressWithoutPreseededState() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.AlertView a = alert(8, "critical", "2024-01-01T01:00:00Z");
    a.contextFlags.add("comfort_care");
    assertTrue(GovernancePolicy.evaluate(a, state, config).reason.startsWith("context:"));
    assertTrue(state.contextFlags.contains("comfort_care"));
  }

  @Test
  void contextFlagsClearOnEncounterChange() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.AlertView first = alert(8, "critical", "2024-01-01T01:00:00Z");
    first.encounterId = "Encounter/1";
    first.contextFlags.add("comfort_care");
    assertTrue(GovernancePolicy.evaluate(first, state, config).reason.startsWith("context:"));
    assertTrue(state.contextFlags.contains("comfort_care"));

    GovernancePolicy.AlertView next = alert(8, "critical", "2024-02-01T01:00:00Z");
    next.encounterId = "Encounter/2";
    GovernancePolicy.Decision d = GovernancePolicy.evaluate(next, state, config);
    assertTrue(state.contextFlags.isEmpty());
    assertTrue(d.emit);
    assertEquals("pass", d.reason);
  }

  @Test
  void contextFlagsDoNotLeakFromUnsetEncounterIntoFirst() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.AlertView first = alert(8, "critical", "2024-01-01T01:00:00Z");
    first.contextFlags.add("comfort_care");
    assertTrue(GovernancePolicy.evaluate(first, state, config).reason.startsWith("context:"));
    assertTrue(state.contextFlags.contains("comfort_care"));

    GovernancePolicy.AlertView next = alert(8, "critical", "2024-01-01T02:00:00Z");
    next.encounterId = "Encounter/1";
    GovernancePolicy.Decision d = GovernancePolicy.evaluate(next, state, config);
    assertTrue(state.contextFlags.isEmpty());
    assertEquals("Encounter/1", state.encounterId);
    assertTrue(d.emit);
    assertEquals("pass", d.reason);
  }

  @Test
  void contextFlagsStickyWithinSameEncounter() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.AlertView first = alert(8, "critical", "2024-01-01T01:00:00Z");
    first.encounterId = "Encounter/1";
    first.contextFlags.add("comfort_care");
    assertTrue(GovernancePolicy.evaluate(first, state, config).reason.startsWith("context:"));

    GovernancePolicy.AlertView next = alert(8, "critical", "2024-01-01T03:00:00Z");
    next.encounterId = "Encounter/1";
    GovernancePolicy.Decision d = GovernancePolicy.evaluate(next, state, config);
    assertTrue(state.contextFlags.contains("comfort_care"));
    assertFalse(d.emit);
    assertTrue(d.reason.startsWith("context:"));
  }

  @Test
  void pageGateDowngradesInterruptiveToWatch() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    config.refractoryMs = 0;
    config.pageGateEnabled = true;
    config.pageMinCrossings = 2;
    config.pageTrajectoryPersistenceMs = 0;
    config.pageMinScoreDelta = 1;
    config.pageMinPositiveComponents = 0;

    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.Decision first =
        GovernancePolicy.evaluate(alert(4, "urgent", "2024-01-01T00:00:00Z"), state, config);
    assertTrue(first.emit);
    assertEquals("passive", first.routing);
    assertEquals("pass_watch:page_crossings", first.reason);

    GovernancePolicy.Decision second =
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T01:00:00Z"), state, config);
    assertTrue(second.emit);
    assertEquals("interruptive", second.routing);
    assertEquals("pass", second.reason);
  }

  @Test
  void belowThresholdResetsTrajectory() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 2;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T00:00:00Z"), state, config);
    assertEquals(1, state.crossingsAboveThreshold);
    GovernancePolicy.Decision d =
        GovernancePolicy.evaluate(alert(1, "none", "2024-01-01T00:10:00Z"), state, config);
    assertEquals("below_threshold", d.reason);
    assertEquals(0, state.crossingsAboveThreshold);
  }

  @Test
  void baselineExpiresAfterLookback() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = true;
    config.baselineLookbackMs = 60_000L;
    config.baselineDeltaThreshold = 2;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    assertEquals(
        "baseline_init",
        GovernancePolicy.evaluate(alert(4, "urgent", "2024-01-01T00:00:00Z"), state, config)
            .reason);
    assertEquals(
        "below_baseline_delta",
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T00:00:30Z"), state, config)
            .reason);
    // After lookback, baseline clears and re-inits
    assertEquals(
        "baseline_init",
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T00:02:00Z"), state, config)
            .reason);
  }

  @Test
  void lateOutOfOrderDoesNotMutateState() {
    GovernancePolicy.Config config = new GovernancePolicy.Config();
    config.baselineEnabled = false;
    config.trajectoryPersistenceMs = 0;
    config.minCrossings = 1;
    config.refractoryMs = 0;
    config.pageGateEnabled = false;

    GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
    GovernancePolicy.Decision first =
        GovernancePolicy.evaluate(alert(5, "urgent", "2024-01-01T01:00:00Z"), state, config);
    assertTrue(first.emit);
    int crossings = state.crossingsAboveThreshold;

    GovernancePolicy.Decision late =
        GovernancePolicy.evaluate(alert(8, "critical", "2024-01-01T00:30:00Z"), state, config);
    assertFalse(late.emit);
    assertEquals("late_out_of_order", late.reason);
    assertEquals(crossings, state.crossingsAboveThreshold);
  }
}
