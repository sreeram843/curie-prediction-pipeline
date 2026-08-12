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
        SofaScorer.compute("Patient/t0-insuff", null, 0L, inputs, "sepsis-sofa", "0.2.0", 3);
    assertEquals(Completeness.INSUFFICIENT_DATA, r.completeness);
    assertNull(r.totalScore);
  }

  @Test
  void vasopressorLadder() {
    ComponentInput low = new ComponentInput(Component.CARDIOVASCULAR);
    low.vasopressorAgent = "dobutamine";
    assertEquals(2, SofaScorer.scoreCardiovascular(low));

    ComponentInput mid = new ComponentInput(Component.CARDIOVASCULAR);
    mid.vasopressorAgent = "norepinephrine";
    mid.vasopressorDoseUgKgMin = 0.05;
    assertEquals(3, SofaScorer.scoreCardiovascular(mid));

    ComponentInput high = new ComponentInput(Component.CARDIOVASCULAR);
    high.vasopressorAgent = "norepinephrine";
    high.vasopressorDoseUgKgMin = 0.2;
    assertEquals(4, SofaScorer.scoreCardiovascular(high));

    ComponentInput unknown = new ComponentInput(Component.CARDIOVASCULAR);
    unknown.onVasopressors = true;
    assertEquals(3, SofaScorer.scoreCardiovascular(unknown));
  }

  @Test
  void respirationRequiresVentForHighPoints() {
    ComponentInput noVent = new ComponentInput(Component.RESPIRATION);
    noVent.pao2Fio2 = 80.0;
    noVent.mechanicallyVentilated = false;
    assertEquals(2, SofaScorer.scoreRespiration(noVent));

    ComponentInput vent = new ComponentInput(Component.RESPIRATION);
    vent.pao2Fio2 = 80.0;
    vent.mechanicallyVentilated = true;
    assertEquals(4, SofaScorer.scoreRespiration(vent));
  }

  @Test
  void spo2WithoutFio2DoesNotAssumeAmbientAir() {
    ComponentInput alone = new ComponentInput(Component.RESPIRATION);
    alone.spo2Percent = 98.0;
    assertNull(SofaScorer.effectiveRatio(alone));
    assertNull(SofaScorer.scoreRespiration(alone));

    ComponentInput withFio2 = new ComponentInput(Component.RESPIRATION);
    withFio2.spo2Percent = 98.0;
    withFio2.fio2Fraction = 0.4;
    assertEquals(245.0, SofaScorer.effectiveRatio(withFio2));
    assertEquals(2, SofaScorer.scoreRespiration(withFio2));
  }
}
