package com.curie.sofa.aki;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AkiScorerTest {

  @Test
  void stage2FromRatio() {
    AkiScorer.Input in = new AkiScorer.Input();
    in.creatinineMgDl = 2.2;
    in.baselineCreatinineMgDl = 1.0;
    AkiScorer.Result r = AkiScorer.compute("Patient/a", null, 0L, in, "0.2.0");
    assertEquals(2, r.stage);
    assertEquals(4, r.totalScore);
    assertEquals("complete", r.completeness);
  }

  @Test
  void absoluteWithoutBaseline() {
    AkiScorer.Input in = new AkiScorer.Input();
    in.creatinineMgDl = 4.2;
    AkiScorer.Result r = AkiScorer.compute("Patient/a", null, 0L, in, "0.2.0");
    assertEquals(3, r.stage);
    assertEquals(6, r.totalScore);
    assertTrue(r.missingComponents.contains("baseline_creatinine"));
    assertEquals("partial", r.completeness);
  }

  @Test
  void urineOliguriaWithoutCrRise() {
    AkiScorer.Input in = new AkiScorer.Input();
    in.creatinineMgDl = 1.0;
    in.baselineCreatinineMgDl = 1.0;
    in.urineMlKgH = 0.4;
    in.urineDurationHours = 14.0;
    AkiScorer.Result r = AkiScorer.compute("Patient/a", null, 0L, in, "0.2.0");
    assertEquals(0, r.creatinineStage);
    assertEquals(2, r.urineStage);
    assertEquals(2, r.stage);
    assertEquals(4, r.totalScore);
  }
}
