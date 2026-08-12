package com.curie.sofa.operators;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.governance.GovernancePolicy;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** CURIE-007: governance decisions from shared cross_runtime_parity.v1.json */
class CrossRuntimeGovParityTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  void governanceDecisionsMatchPythonContract() throws Exception {
    int n = 0;
    try (InputStream in =
        CrossRuntimeGovParityTest.class.getResourceAsStream(
            "/golden/cross_runtime_parity.v1.json")) {
      JsonNode root = MAPPER.readTree(in);
      for (JsonNode c : root.get("governance_decisions")) {
        n++;
        GovernancePolicy.Config config = configFrom(c.get("config"));
        GovernancePolicy.PatientGovState state = new GovernancePolicy.PatientGovState();
        Iterator<JsonNode> alerts = c.get("alerts").elements();
        Iterator<JsonNode> expects = c.get("expect").elements();
        while (alerts.hasNext() && expects.hasNext()) {
          JsonNode alert = alerts.next();
          JsonNode expect = expects.next();
          GovernancePolicy.AlertView view = new GovernancePolicy.AlertView();
          view.score = alert.get("score").asInt();
          view.tier = alert.get("tier").asText();
          view.eventTime = alert.get("event_time").asText();
          if (alert.has("positive_components")) {
            view.positiveComponents = alert.get("positive_components").asInt();
          }
          if (alert.has("context_flags")) {
            for (JsonNode f : alert.get("context_flags")) {
              view.contextFlags.add(f.asText());
            }
          }
          GovernancePolicy.Decision d = GovernancePolicy.evaluate(view, state, config);
          assertEquals(expect.get("emit").asBoolean(), d.emit, c.get("id").asText());
          assertEquals(expect.get("reason").asText(), d.reason, c.get("id").asText());
          assertEquals(expect.get("routing").asText(), d.routing, c.get("id").asText());
        }
      }
    }
    assertTrue(n >= 1, "expected governance fixtures");
  }

  private static GovernancePolicy.Config configFrom(JsonNode raw) {
    GovernancePolicy.Config c = new GovernancePolicy.Config();
    if (raw.has("trajectory_persistence_minutes")) {
      c.trajectoryPersistenceMs = raw.get("trajectory_persistence_minutes").asInt() * 60_000L;
    }
    if (raw.has("min_crossings")) {
      c.minCrossings = raw.get("min_crossings").asInt();
    }
    if (raw.has("baseline_enabled")) {
      c.baselineEnabled = raw.get("baseline_enabled").asBoolean();
    }
    if (raw.has("refractory_minutes")) {
      c.refractoryMs = raw.get("refractory_minutes").asInt() * 60_000L;
    }
    if (raw.has("page_gate_enabled")) {
      c.pageGateEnabled = raw.get("page_gate_enabled").asBoolean();
    }
    if (raw.has("page_min_crossings")) {
      c.pageMinCrossings = raw.get("page_min_crossings").asInt();
    }
    if (raw.has("page_trajectory_persistence_minutes")) {
      c.pageTrajectoryPersistenceMs =
          raw.get("page_trajectory_persistence_minutes").asInt() * 60_000L;
    }
    if (raw.has("page_min_score_delta")) {
      c.pageMinScoreDelta = raw.get("page_min_score_delta").asInt();
    }
    if (raw.has("page_min_positive_components")) {
      c.pageMinPositiveComponents = raw.get("page_min_positive_components").asInt();
    }
    if (raw.has("suppression_flags")) {
      Set<String> flags = new HashSet<>();
      for (JsonNode f : raw.get("suppression_flags")) {
        flags.add(f.asText());
      }
      c.suppressionFlags = flags;
    }
    return c;
  }
}
