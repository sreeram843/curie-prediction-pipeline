package com.curie.sofa.state;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import java.util.List;
import org.junit.jupiter.api.Test;

/** Mirrors {@code eval/sofa/test_stream_scorer.py} per-value freshness/expiry scenarios. */
class PatientSofaStateTest {

  private static long h(double hours) {
    return (long) (hours * 3_600_000);
  }

  private static ComponentInput byName(List<ComponentInput> inputs, Component name) {
    return inputs.stream().filter(i -> i.name == name).findFirst().orElseThrow();
  }

  @Test
  void ignoresOlderValueForSameField() {
    PatientSofaState state = new PatientSofaState();
    ComponentInput newer = new ComponentInput(Component.COAGULATION);
    newer.platelets10e9L = 150.0;
    ComponentInput older = new ComponentInput(Component.COAGULATION);
    older.platelets10e9L = 40.0;
    assertTrue(state.apply(newer, h(2), 1L));
    assertFalse(state.apply(older, h(1), 2L));
    ComponentInput snapshot = byName(state.snapshotInputs(h(2)), Component.COAGULATION);
    assertEquals(150.0, snapshot.platelets10e9L);
  }

  @Test
  void partialUpdateDoesNotRefreshUnrelatedField() {
    PatientSofaState state = new PatientSofaState();
    ComponentInput platelets = new ComponentInput(Component.COAGULATION);
    platelets.platelets10e9L = 150.0;
    ComponentInput bili = new ComponentInput(Component.LIVER);
    bili.bilirubinMgDl = 2.0;
    state.apply(platelets, h(0), 1L);
    state.apply(bili, h(0), 2L);
    // 30h later only platelets update → bilirubin is beyond its 24h TTL.
    ComponentInput freshPlatelets = new ComponentInput(Component.COAGULATION);
    freshPlatelets.platelets10e9L = 100.0;
    state.apply(freshPlatelets, h(30), 3L);
    ComponentInput liver = byName(state.snapshotInputs(h(30)), Component.LIVER);
    assertNull(liver.bilirubinMgDl);
    ComponentInput coag = byName(state.snapshotInputs(h(30)), Component.COAGULATION);
    assertEquals(100.0, coag.platelets10e9L);
  }

  @Test
  void olderEventMayCarryNewestValueForAnotherField() {
    PatientSofaState state = new PatientSofaState();
    ComponentInput spo2 = new ComponentInput(Component.RESPIRATION);
    spo2.spo2Percent = 96.0;
    state.apply(spo2, h(2), 1L);
    ComponentInput fio2 = new ComponentInput(Component.RESPIRATION);
    fio2.fio2Fraction = 0.4;
    assertTrue(state.apply(fio2, h(1), 2L)); // per-field: FiO2 field has no newer value
    ComponentInput resp = byName(state.snapshotInputs(h(2)), Component.RESPIRATION);
    assertEquals(96.0, resp.spo2Percent);
    assertEquals(0.4, resp.fio2Fraction);
  }

  @Test
  void mapExpiresFasterThanLabs() {
    PatientSofaState state = new PatientSofaState();
    ComponentInput map = new ComponentInput(Component.CARDIOVASCULAR);
    map.mapMmhg = 65.0;
    ComponentInput cr = new ComponentInput(Component.RENAL);
    cr.creatinineMgDl = 3.0;
    state.apply(map, h(0), 1L);
    state.apply(cr, h(0), 2L);
    assertEquals(3_600_000L, PatientSofaState.VALUE_TTL_MS.get("mapMmhg"));
    assertEquals(24L * 3_600_000, PatientSofaState.VALUE_TTL_MS.get("creatinineMgDl"));
    ComponentInput cv = byName(state.snapshotInputs(h(2)), Component.CARDIOVASCULAR);
    ComponentInput renal = byName(state.snapshotInputs(h(2)), Component.RENAL);
    assertNull(cv.mapMmhg);
    assertEquals(3.0, renal.creatinineMgDl);
  }

  @Test
  void expiredValueDropsItsEvidence() {
    PatientSofaState state = new PatientSofaState();
    ComponentInput map = new ComponentInput(Component.CARDIOVASCULAR);
    map.mapMmhg = 65.0;
    map.evidenceIds.add("Observation/map");
    state.apply(map, h(0), 1L);
    ComponentInput cv = byName(state.snapshotInputs(h(5)), Component.CARDIOVASCULAR);
    assertNull(cv.mapMmhg);
    assertTrue(cv.evidenceIds.isEmpty());
  }

  @Test
  void encounterChangeClearsState() {
    PatientSofaState state = new PatientSofaState();
    state.encounterId = "Encounter/1";
    ComponentInput in = new ComponentInput(Component.RENAL);
    in.creatinineMgDl = 3.0;
    state.apply(in, h(0), 1L);
    state.resetForEncounter("Encounter/2");
    assertTrue(state.values.isEmpty());
    assertEquals("Encounter/2", state.encounterId);
  }
}
