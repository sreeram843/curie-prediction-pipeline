package com.curie.sofa.resp;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class RespScorerTest {

  @Test
  void roomAirCompleteOk() {
    RespScorer.Input in = new RespScorer.Input();
    in.spo2Percent = 98.0;
    in.roomAir = true;
    in.respiratoryRate = 16.0;
    in.oxygenDevice = "none";
    RespScorer.Result r = RespScorer.compute("Patient/1", null, 1_000L, in, "0.1.0");
    assertEquals(0, r.stage);
    assertEquals(0, r.totalScore);
    assertEquals("complete", r.completeness);
    assertEquals("none", RespScorer.tierForScore(r.totalScore, 2));
  }

  @Test
  void spo2AloneInsufficient() {
    RespScorer.Input in = new RespScorer.Input();
    in.spo2Percent = 88.0;
    RespScorer.Result r = RespScorer.compute("Patient/1", null, 1_000L, in, "0.1.0");
    assertNull(r.stage);
    assertNull(r.totalScore);
    assertEquals("insufficient_data", r.completeness);
  }

  @Test
  void mildSfRatioStages() {
    RespScorer.Input in = new RespScorer.Input();
    in.spo2Percent = 92.0;
    in.fio2Fraction = 0.28;
    in.respiratoryRate = 20.0;
    in.oxygenDevice = "nasal_cannula";
    RespScorer.Result r = RespScorer.compute("Patient/1", null, 1_000L, in, "0.1.0");
    // 92/0.28 ≈ 328.6 → oxygenation stage 1; device stage 1 → max 1 → score 2
    assertEquals(1, r.stage);
    assertEquals(2, r.totalScore);
    assertEquals("watch", RespScorer.tierForScore(r.totalScore, 2));
  }
}
