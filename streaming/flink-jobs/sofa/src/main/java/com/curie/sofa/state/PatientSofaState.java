package com.curie.sofa.state;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/** Per-patient (encounter) rolling SOFA feature state held in Flink keyed state. */
public class PatientSofaState implements Serializable {
  public String patientId;
  public String encounterId;
  public final Map<Component, ComponentInput> latest = new EnumMap<>(Component.class);

  public void apply(ComponentInput update) {
    ComponentInput existing = latest.get(update.name);
    if (existing == null) {
      latest.put(update.name, copy(update));
      return;
    }
    merge(existing, update);
  }

  public List<ComponentInput> snapshotInputs() {
    List<ComponentInput> out = new ArrayList<>();
    for (Component c : Component.values()) {
      ComponentInput in = latest.get(c);
      out.add(in != null ? copy(in) : new ComponentInput(c));
    }
    return out;
  }

  private static ComponentInput copy(ComponentInput src) {
    ComponentInput n = new ComponentInput(src.name);
    n.pao2Fio2 = src.pao2Fio2;
    n.spo2Fio2 = src.spo2Fio2;
    n.mechanicallyVentilated = src.mechanicallyVentilated;
    n.platelets10e9L = src.platelets10e9L;
    n.bilirubinMgDl = src.bilirubinMgDl;
    n.mapMmhg = src.mapMmhg;
    n.onVasopressors = src.onVasopressors;
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
