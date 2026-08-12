package com.curie.sofa.model;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AlertIdsTest {

  @Test
  void deterministicAcrossCalls() {
    String a = AlertIds.of("Patient/1", "Encounter/9", "sepsis", 7, 1_700_000_000_000L, "0.2.0");
    String b = AlertIds.of("Patient/1", "Encounter/9", "sepsis", 7, 1_700_000_000_000L, "0.2.0");
    assertEquals(a, b);
    assertTrue(a.startsWith("alert-"));
  }

  @Test
  void encounterChangesId() {
    String a = AlertIds.of("Patient/1", "Encounter/1", "sepsis", 7, 100L, "0.2.0");
    String b = AlertIds.of("Patient/1", "Encounter/2", "sepsis", 7, 100L, "0.2.0");
    assertTrue(!a.equals(b));
  }
}
