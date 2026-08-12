package com.curie.sofa.state;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * Per-patient encounter-scoped SOFA feature state.
 *
 * <p>Each component keeps the latest observation by <em>event time</em>. Older updates are ignored
 * (late/out-of-order). Encounter changes clear component state.
 */
public class PatientSofaState implements Serializable {
  public String patientId;
  public String encounterId;
  public final Map<Component, TimedComponent> latest = new EnumMap<>(Component.class);

  public static final class TimedComponent implements Serializable {
    public ComponentInput input;
    public long eventTimeMs;
    public long ingestTimeMs;
  }

  /** @return true if state was applied; false if ignored as stale */
  public boolean apply(ComponentInput update, long eventTimeMs, long ingestTimeMs) {
    TimedComponent existing = latest.get(update.name);
    if (existing == null) {
      TimedComponent slot = new TimedComponent();
      slot.input = copy(update);
      slot.eventTimeMs = eventTimeMs;
      slot.ingestTimeMs = ingestTimeMs;
      latest.put(update.name, slot);
      return true;
    }
    if (eventTimeMs < existing.eventTimeMs) {
      return false; // stale / out-of-order
    }
    if (eventTimeMs == existing.eventTimeMs && ingestTimeMs < existing.ingestTimeMs) {
      return false;
    }
    merge(existing.input, update);
    existing.eventTimeMs = eventTimeMs;
    existing.ingestTimeMs = ingestTimeMs;
    return true;
  }

  public void resetForEncounter(String newEncounterId) {
    latest.clear();
    encounterId = newEncounterId;
  }

  public List<ComponentInput> snapshotInputs() {
    List<ComponentInput> out = new ArrayList<>();
    for (Component c : Component.values()) {
      TimedComponent slot = latest.get(c);
      out.add(slot != null ? copy(slot.input) : new ComponentInput(c));
    }
    return out;
  }

  private static ComponentInput copy(ComponentInput src) {
    ComponentInput n = new ComponentInput(src.name);
    n.pao2Fio2 = src.pao2Fio2;
    n.spo2Fio2 = src.spo2Fio2;
    n.spo2Percent = src.spo2Percent;
    n.pao2Mmhg = src.pao2Mmhg;
    n.fio2Fraction = src.fio2Fraction;
    n.mechanicallyVentilated = src.mechanicallyVentilated;
    n.platelets10e9L = src.platelets10e9L;
    n.bilirubinMgDl = src.bilirubinMgDl;
    n.mapMmhg = src.mapMmhg;
    n.onVasopressors = src.onVasopressors;
    n.vasopressorAgent = src.vasopressorAgent;
    n.vasopressorDoseUgKgMin = src.vasopressorDoseUgKgMin;
    n.gcs = src.gcs;
    n.creatinineMgDl = src.creatinineMgDl;
    n.urineOutputMlDay = src.urineOutputMlDay;
    n.evidenceIds.addAll(src.evidenceIds);
    return n;
  }

  private static void merge(ComponentInput dst, ComponentInput src) {
    if (src.pao2Fio2 != null) {
      dst.pao2Fio2 = src.pao2Fio2;
    }
    if (src.spo2Fio2 != null) {
      dst.spo2Fio2 = src.spo2Fio2;
    }
    if (src.spo2Percent != null) {
      dst.spo2Percent = src.spo2Percent;
    }
    if (src.pao2Mmhg != null) {
      dst.pao2Mmhg = src.pao2Mmhg;
    }
    if (src.fio2Fraction != null) {
      dst.fio2Fraction = src.fio2Fraction;
    }
    if (src.mechanicallyVentilated != null) {
      dst.mechanicallyVentilated = src.mechanicallyVentilated;
    }
    if (src.platelets10e9L != null) {
      dst.platelets10e9L = src.platelets10e9L;
    }
    if (src.bilirubinMgDl != null) {
      dst.bilirubinMgDl = src.bilirubinMgDl;
    }
    if (src.mapMmhg != null) {
      dst.mapMmhg = src.mapMmhg;
    }
    if (src.onVasopressors != null) {
      dst.onVasopressors = src.onVasopressors;
    }
    if (src.vasopressorAgent != null) {
      dst.vasopressorAgent = src.vasopressorAgent;
    }
    if (src.vasopressorDoseUgKgMin != null) {
      dst.vasopressorDoseUgKgMin = src.vasopressorDoseUgKgMin;
    }
    if (src.gcs != null) {
      dst.gcs = src.gcs;
    }
    if (src.creatinineMgDl != null) {
      dst.creatinineMgDl = src.creatinineMgDl;
    }
    if (src.urineOutputMlDay != null) {
      dst.urineOutputMlDay = src.urineOutputMlDay;
    }
    for (String e : src.evidenceIds) {
      if (!dst.evidenceIds.contains(e)) {
        dst.evidenceIds.add(e);
      }
    }
  }
}
