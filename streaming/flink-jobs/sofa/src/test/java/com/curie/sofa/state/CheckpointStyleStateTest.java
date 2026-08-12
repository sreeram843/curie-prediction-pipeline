package com.curie.sofa.state;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.aki.PatientAkiState;
import com.curie.sofa.scoring.SofaScorer;
import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import org.junit.jupiter.api.Test;

/** Serialize/restore feature state to approximate Flink checkpoint + restart. */
class CheckpointStyleStateTest {

  @SuppressWarnings("unchecked")
  private static <T> T roundTrip(T value) throws Exception {
    ByteArrayOutputStream bos = new ByteArrayOutputStream();
    try (ObjectOutputStream oos = new ObjectOutputStream(bos)) {
      oos.writeObject(value);
    }
    try (ObjectInputStream ois =
        new ObjectInputStream(new ByteArrayInputStream(bos.toByteArray()))) {
      return (T) ois.readObject();
    }
  }

  @Test
  void sofaStateSurvivesSerializeAndKeepsMergedRatioInputs() throws Exception {
    PatientSofaState state = new PatientSofaState();
    state.patientId = "Patient/1";
    state.encounterId = "Encounter/1";

    ComponentInput spo2 = new ComponentInput(Component.RESPIRATION);
    spo2.spo2Percent = 96.0;
    spo2.evidenceIds.add("Observation/spo2");
    assertTrue(state.apply(spo2, 1_000L, 1L));

    ComponentInput fio2 = new ComponentInput(Component.RESPIRATION);
    fio2.fio2Fraction = 0.5;
    fio2.evidenceIds.add("Observation/fio2");
    assertTrue(state.apply(fio2, 2_000L, 2L));

    PatientSofaState restored = roundTrip(state);
    ComponentInput resp = restored.latest.get(Component.RESPIRATION).input;
    assertEquals(96.0, resp.spo2Percent);
    assertEquals(0.5, resp.fio2Fraction);
    assertEquals(192.0, SofaScorer.effectiveRatio(resp));
  }

  @Test
  void akiStateSurvivesSerializeAndRejectsStaleCreatinine() throws Exception {
    PatientAkiState state = new PatientAkiState();
    state.patientId = "Patient/aki";
    assertTrue(state.applyCreatinine(1.0, 1_000L, "Observation/cr1", false));
    assertTrue(state.applyCreatinine(2.2, 2_000L, "Observation/cr2", false));

    PatientAkiState restored = roundTrip(state);
    assertEquals(2.2, restored.creatinineMgDl);
    assertFalse(restored.applyCreatinine(9.0, 1_500L, "Observation/late", false));
    assertEquals(2.2, restored.creatinineMgDl);
  }
}
