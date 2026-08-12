package com.curie.sofa.aki;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

class PatientAkiUrineTest {

  private final ObjectMapper mapper = new ObjectMapper();

  @Test
  void urineRateAndDurationStageViaApplyUrine() {
    PatientAkiState state = new PatientAkiState();
    assertTrue(state.applyUrine(0.4, 14.0, null, 1_000L, "Observation/uo-1"));
    AkiScorer.Result r = AkiScorer.compute("Patient/1", null, 1_000L, state.toInput(), "0.2.0");
    assertEquals(2, r.urineStage);
    assertEquals(4, r.totalScore);
  }

  @Test
  void fhirStyleUrineObservationShape() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "uo-1");
    obs.put("status", "final");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", AkiAlertFunction.LOINC_URINE_OUTPUT);
    obs.putObject("valueQuantity").put("value", 0.25).put("unit", "mL/kg/h");
    ObjectNode duration = obs.putArray("component").addObject();
    duration
        .putObject("code")
        .putArray("coding")
        .addObject()
        .put("code", AkiAlertFunction.COMPONENT_DURATION_HOURS);
    duration.putObject("valueQuantity").put("value", 24).put("unit", "h");

    // Exercise the same field extraction helpers via state apply as AkiAlertFunction does
    PatientAkiState state = new PatientAkiState();
    double rate = obs.path("valueQuantity").path("value").asDouble();
    double hours =
        obs.path("component").get(0).path("valueQuantity").path("value").asDouble();
    assertTrue(state.applyUrine(rate, hours, null, 2_000L, "Observation/uo-1"));
    AkiScorer.Result r = AkiScorer.compute("Patient/1", null, 2_000L, state.toInput(), "0.2.0");
    assertEquals(3, r.urineStage);
  }
}
