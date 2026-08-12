package com.curie.sofa.aki;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class AkiTimelineTest {

  private static long ms(String iso) {
    return Instant.parse(iso).toEpochMilli();
  }

  @Test
  void stage1DeltaWithin48h() {
    AkiTimeline.State state = new AkiTimeline.State();
    AkiTimeline.CrObs a = new AkiTimeline.CrObs();
    a.eventTimeMs = ms("2024-07-01T00:00:00Z");
    a.valueMgDl = 1.0;
    a.evidenceId = "Observation/cr-0";
    AkiTimeline.CrObs b = new AkiTimeline.CrObs();
    b.eventTimeMs = ms("2024-07-02T12:00:00Z");
    b.valueMgDl = 1.35;
    b.evidenceId = "Observation/cr-1";
    state.ingestCreatinine(a);
    state.ingestCreatinine(b);
    AkiTimeline.Result r = AkiTimeline.evaluate(state, b.eventTimeMs);
    assertEquals(1, r.stage);
    assertTrue(r.criteriaMet.contains("delta_cr_ge_0_3_within_48h"));
    assertEquals(1.0, r.baseline7dMgDl);
  }

  @Test
  void outOfOrderIngestMatchesSorted() {
    AkiTimeline.State forward = new AkiTimeline.State();
    AkiTimeline.State reverse = new AkiTimeline.State();
    AkiTimeline.CrObs a = new AkiTimeline.CrObs();
    a.eventTimeMs = ms("2024-07-01T00:00:00Z");
    a.valueMgDl = 1.0;
    a.evidenceId = "Observation/a";
    AkiTimeline.CrObs b = new AkiTimeline.CrObs();
    b.eventTimeMs = ms("2024-07-02T00:00:00Z");
    b.valueMgDl = 2.0;
    b.evidenceId = "Observation/b";
    forward.ingestCreatinine(a);
    forward.ingestCreatinine(b);
    reverse.ingestCreatinine(b);
    reverse.ingestCreatinine(a);
    AkiTimeline.Result rf = AkiTimeline.evaluate(forward, b.eventTimeMs);
    AkiTimeline.Result rr = AkiTimeline.evaluate(reverse, b.eventTimeMs);
    assertEquals(rf.stage, rr.stage);
    assertEquals(2, rf.stage);
    assertEquals(rf.baseline7dMgDl, rr.baseline7dMgDl);
  }

  @Test
  void missingWeightDoesNotInventUoStage() {
    AkiTimeline.State state = new AkiTimeline.State();
    AkiTimeline.UoObs u = new AkiTimeline.UoObs();
    u.endTimeMs = ms("2024-07-01T06:00:00Z");
    u.volumeMl = 100.0;
    u.durationHours = 6.0;
    u.evidenceId = "Observation/uo";
    state.ingestUrine(u);
    AkiTimeline.CrObs c = new AkiTimeline.CrObs();
    c.eventTimeMs = u.endTimeMs;
    c.valueMgDl = 1.0;
    c.evidenceId = "Observation/cr";
    state.ingestCreatinine(c);
    AkiTimeline.Result r = AkiTimeline.evaluate(state, u.endTimeMs);
    assertEquals(0, r.stage);
    assertNull(r.urineStage);
    assertTrue(r.missingComponents.contains("weight_kg"));
  }

  @Test
  void esrdExcluded() {
    AkiTimeline.State state = new AkiTimeline.State();
    state.flags.add("esrd");
    AkiTimeline.CrObs c = new AkiTimeline.CrObs();
    c.eventTimeMs = ms("2024-07-01T00:00:00Z");
    c.valueMgDl = 5.0;
    c.evidenceId = "Observation/cr";
    state.ingestCreatinine(c);
    AkiTimeline.Result r = AkiTimeline.evaluate(state, c.eventTimeMs);
    assertEquals("excluded", r.status);
    assertNull(r.stage);
  }
}
