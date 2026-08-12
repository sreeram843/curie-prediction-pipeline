package com.curie.sofa.hemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class HemoScorerTest {

  @Test
  void lactateAndMapStage() {
    HemoScorer.Input in = new HemoScorer.Input();
    in.lactateMmolL = 2.5;
    in.mapMmhg = 60.0;
    HemoScorer.Result r = HemoScorer.compute("Patient/1", null, 1_000L, in, "0.1.0");
    assertEquals(2, r.stage);
    assertEquals(4, r.totalScore);
    assertEquals("complete", r.completeness);
    assertTrue(r.criteriaMet.contains("lactate_ge_2"));
    assertTrue(r.criteriaMet.contains("map_lt_65"));
  }

  @Test
  void insufficientWithoutInputs() {
    HemoScorer.Input in = new HemoScorer.Input();
    HemoScorer.Result r = HemoScorer.compute("Patient/1", null, 1_000L, in, "0.1.0");
    assertNull(r.stage);
    assertEquals("insufficient_data", r.completeness);
  }
}
