package com.curie.sofa.state;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import org.junit.jupiter.api.Test;

class PatientSofaStateTest {

  @Test
  void ignoresOlderEventTime() {
    PatientSofaState state = new PatientSofaState();
    ComponentInput newer = new ComponentInput(Component.COAGULATION);
    newer.platelets10e9L = 40.0;
    ComponentInput older = new ComponentInput(Component.COAGULATION);
    older.platelets10e9L = 10.0;
    assertTrue(state.apply(newer, 2_000L, 2_000L));
    assertFalse(state.apply(older, 1_000L, 3_000L));
    assertEquals(40.0, state.latest.get(Component.COAGULATION).input.platelets10e9L);
  }

  @Test
  void encounterChangeClearsState() {
    PatientSofaState state = new PatientSofaState();
    state.encounterId = "Encounter/1";
    ComponentInput in = new ComponentInput(Component.RENAL);
    in.creatinineMgDl = 3.0;
    state.apply(in, 1_000L, 1_000L);
    state.resetForEncounter("Encounter/2");
    assertTrue(state.latest.isEmpty());
    assertEquals("Encounter/2", state.encounterId);
  }
}
