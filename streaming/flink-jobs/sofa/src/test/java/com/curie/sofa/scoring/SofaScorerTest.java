package com.curie.sofa.scoring;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.curie.sofa.scoring.SofaScorer.Completeness;
import com.curie.sofa.scoring.SofaScorer.ScoreResult;
import com.curie.sofa.scoring.SofaScorer.Tier;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SofaScorerTest {

  private static List<ComponentInput> fullMild() {
    List<ComponentInput> inputs = new ArrayList<>();
    ComponentInput resp = new ComponentInput(Component.RESPIRATION);
    resp.pao2Fio2 = 450.0;
    resp.evidenceIds.add("Observation/resp-1");
    inputs.add(resp);

    ComponentInput coag = new ComponentInput(Component.COAGULATION);
    coag.platelets10e9L = 200.0;
    coag.evidenceIds.add("Observation/plt-1");
    inputs.add(coag);

    ComponentInput liver = new ComponentInput(Component.LIVER);
    liver.bilirubinMgDl = 0.8;
    liver.evidenceIds.add("Observation/bili-1");
    inputs.add(liver);

    ComponentInput cv = new ComponentInput(Component.CARDIOVASCULAR);
    cv.mapMmhg = 80.0;
    cv.evidenceIds.add("Observation/map-1");
    inputs.add(cv);

    ComponentInput cns = new ComponentInput(Component.CNS);
    cns.gcs = 15;
    cns.evidenceIds.add("Observation/gcs-1");
    inputs.add(cns);

    ComponentInput renal = new ComponentInput(Component.RENAL);
    renal.creatinineMgDl = 0.9;
    renal.evidenceIds.add("Observation/cr-1");
    inputs.add(renal);
    return inputs;
  }

  @Test
  void completeZeroScore() {
    ScoreResult r =
        SofaScorer.compute("Patient/t0-zero", null, 0L, fullMild(), "sepsis-sofa", "0.1.0", 3);
    assertEquals(Completeness.COMPLETE, r.completeness);
    assertEquals(0, r.totalScore);
    assertTrue(r.missingComponents.isEmpty());
    assertEquals(Tier.NONE, SofaScorer.tierForScore(r.totalScore, 2));
  }

  @Test
  void completeElevatedScore() {
    List<ComponentInput> inputs = fullMild();
    for (ComponentInput in : inputs) {
      if (in.name == Component.COAGULATION) {
        in.platelets10e9L = 40.0;
      }
      if (in.name == Component.LIVER) {
        in.bilirubinMgDl = 2.5;
      }
      if (in.name == Component.RENAL) {
        in.creatinineMgDl = 2.1;
      }
    }
    ScoreResult r =
        SofaScorer.compute("Patient/t0-high", null, 0L, inputs, "sepsis-sofa", "0.1.0", 3);
    assertEquals(Completeness.COMPLETE, r.completeness);
    assertEquals(7, r.totalScore);
    assertEquals(Tier.CRITICAL, SofaScorer.tierForScore(r.totalScore, 2));
    assertTrue(r.evidenceIds.contains("Observation/plt-1"));
  }

  @Test
  void partialListsMissingComponents() {
    List<ComponentInput> inputs = new ArrayList<>();
    ComponentInput coag = new ComponentInput(Component.COAGULATION);
    coag.platelets10e9L = 40.0;
    inputs.add(coag);
    ComponentInput liver = new ComponentInput(Component.LIVER);
    liver.bilirubinMgDl = 2.5;
    inputs.add(liver);
    ComponentInput renal = new ComponentInput(Component.RENAL);
    renal.creatinineMgDl = 2.1;
    inputs.add(renal);

    ScoreResult r =
        SofaScorer.compute("Patient/t0-partial", null, 0L, inputs, "sepsis-sofa", "0.1.0", 3);
    assertEquals(Completeness.PARTIAL, r.completeness);
    assertEquals(7, r.totalScore);
    assertTrue(r.missingComponents.contains(Component.RESPIRATION));
    assertTrue(r.missingComponents.contains(Component.CNS));
  }

  @Test
  void insufficientData() {
    List<ComponentInput> inputs = new ArrayList<>();
    ComponentInput coag = new ComponentInput(Component.COAGULATION);
    coag.platelets10e9L = 10.0;
    inputs.add(coag);
    ScoreResult r =
        SofaScorer.compute("Patient/t0-insuff", null, 0L, inputs, "sepsis-sofa", "0.1.0", 3);
    assertEquals(Completeness.INSUFFICIENT_DATA, r.completeness);
    assertNull(r.totalScore);
  }
}
