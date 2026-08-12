package com.curie.sofa.operators;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.governance.GovernancePolicy;
import com.curie.sofa.model.RuleBundle;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** CURIE-005: Java configFromBundle matches eval/fixtures/golden/governance_parity.v1.json */
class GovernanceConfigParityTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  @SuppressWarnings("unchecked")
  void parityFixtureMatchesPythonExpect() throws Exception {
    try (InputStream in =
        GovernanceConfigParityTest.class.getResourceAsStream(
            "/golden/governance_parity.v1.json")) {
      Map<String, Object> root = MAPPER.readValue(in, Map.class);
      Map<String, Object> bundleMap = (Map<String, Object>) root.get("bundle");
      RuleBundle bundle = MAPPER.convertValue(bundleMap, RuleBundle.class);
      Map<String, Object> expect = (Map<String, Object>) root.get("expect");

      GovernancePolicy.Config cfg = GovernanceFilterFunction.configFromBundle(bundle);

      assertEquals(
          ((Number) expect.get("trajectory_persistence_minutes")).intValue() * 60_000L,
          cfg.trajectoryPersistenceMs);
      assertEquals(((Number) expect.get("min_crossings")).intValue(), cfg.minCrossings);
      assertEquals(expect.get("baseline_enabled"), cfg.baselineEnabled);
      assertEquals(
          ((Number) expect.get("baseline_lookback_hours")).intValue() * 3_600_000L,
          cfg.baselineLookbackMs);
      assertEquals(
          ((Number) expect.get("baseline_delta_threshold")).intValue(),
          cfg.baselineDeltaThreshold);
      assertEquals(
          ((Number) expect.get("refractory_minutes")).intValue() * 60_000L, cfg.refractoryMs);
      assertEquals(
          ((Number) expect.get("resolution_gap_minutes")).intValue() * 60_000L,
          cfg.resolutionGapMs);
      assertEquals(expect.get("page_gate_enabled"), cfg.pageGateEnabled);
      assertEquals(
          ((Number) expect.get("page_min_crossings")).intValue(), cfg.pageMinCrossings);
      assertEquals(
          ((Number) expect.get("page_trajectory_persistence_minutes")).intValue() * 60_000L,
          cfg.pageTrajectoryPersistenceMs);
      assertEquals(
          ((Number) expect.get("page_min_score_delta")).intValue(), cfg.pageMinScoreDelta);
      assertEquals(
          ((Number) expect.get("page_min_positive_components")).intValue(),
          cfg.pageMinPositiveComponents);

      List<String> flags = (List<String>) expect.get("suppression_flags");
      assertTrue(cfg.suppressionFlags.containsAll(flags));
      List<String> interruptive = (List<String>) expect.get("interruptive_tiers");
      assertTrue(cfg.interruptiveTiers.containsAll(interruptive));
      List<String> passive = (List<String>) expect.get("passive_tiers");
      assertTrue(cfg.passiveTiers.containsAll(passive));
    }
  }

  @Test
  void missingGovernanceUsesDefaults() {
    GovernancePolicy.Config cfg = GovernanceFilterFunction.configFromBundle(null);
    assertEquals(30L * 60_000L, cfg.trajectoryPersistenceMs);
    assertEquals(2, cfg.minCrossings);
    assertTrue(cfg.baselineEnabled);
    assertEquals(60L * 60_000L, cfg.resolutionGapMs);
    assertFalse(cfg.pageGateEnabled);
  }
}
