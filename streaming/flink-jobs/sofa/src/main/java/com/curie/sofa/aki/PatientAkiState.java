package com.curie.sofa.aki;

import java.io.Serializable;

/** Encounter-scoped AKI feature state (current Cr, baseline, optional UO). */
public class PatientAkiState implements Serializable {
  public String patientId;
  public String encounterId;
  public Double creatinineMgDl;
  public long creatinineEventTimeMs = Long.MIN_VALUE;
  public Double baselineCreatinineMgDl;
  public long baselineEventTimeMs = Long.MIN_VALUE;
  public Double urineMlKgH;
  public Double urineDurationHours;
  public Boolean anuria;
  public long urineEventTimeMs = Long.MIN_VALUE;
  public final java.util.ArrayList<String> evidenceIds = new java.util.ArrayList<>();
  public final java.util.ArrayList<String> baselineEvidenceIds = new java.util.ArrayList<>();
  public final java.util.ArrayList<String> urineEvidenceIds = new java.util.ArrayList<>();

  public void resetForEncounter(String encounterId) {
    this.encounterId = encounterId;
    creatinineMgDl = null;
    creatinineEventTimeMs = Long.MIN_VALUE;
    baselineCreatinineMgDl = null;
    baselineEventTimeMs = Long.MIN_VALUE;
    urineMlKgH = null;
    urineDurationHours = null;
    anuria = null;
    urineEventTimeMs = Long.MIN_VALUE;
    evidenceIds.clear();
    baselineEvidenceIds.clear();
    urineEvidenceIds.clear();
  }

  public boolean applyCreatinine(double value, long eventTimeMs, String evidenceId, boolean asBaseline) {
    if (asBaseline) {
      if (baselineEventTimeMs != Long.MIN_VALUE && eventTimeMs < baselineEventTimeMs) {
        return false;
      }
      baselineCreatinineMgDl = value;
      baselineEventTimeMs = eventTimeMs;
      if (evidenceId != null && !baselineEvidenceIds.contains(evidenceId)) {
        baselineEvidenceIds.add(evidenceId);
      }
      return true;
    }
    if (creatinineEventTimeMs != Long.MIN_VALUE && eventTimeMs < creatinineEventTimeMs) {
      return false;
    }
    // First Cr becomes baseline if none yet
    if (baselineCreatinineMgDl == null) {
      baselineCreatinineMgDl = value;
      baselineEventTimeMs = eventTimeMs;
      if (evidenceId != null) {
        baselineEvidenceIds.add(evidenceId);
      }
    }
    creatinineMgDl = value;
    creatinineEventTimeMs = eventTimeMs;
    if (evidenceId != null && !evidenceIds.contains(evidenceId)) {
      evidenceIds.add(evidenceId);
    }
    return true;
  }

  public boolean applyUrine(
      Double mlKgH, Double durationHours, Boolean anuriaFlag, long eventTimeMs, String evidenceId) {
    if (urineEventTimeMs != Long.MIN_VALUE && eventTimeMs < urineEventTimeMs) {
      return false;
    }
    if (mlKgH != null) {
      urineMlKgH = mlKgH;
    }
    if (durationHours != null) {
      urineDurationHours = durationHours;
    }
    if (anuriaFlag != null) {
      anuria = anuriaFlag;
    }
    urineEventTimeMs = eventTimeMs;
    if (evidenceId != null && !urineEvidenceIds.contains(evidenceId)) {
      urineEvidenceIds.add(evidenceId);
    }
    return true;
  }

  public AkiScorer.Input toInput() {
    AkiScorer.Input in = new AkiScorer.Input();
    in.creatinineMgDl = creatinineMgDl;
    in.baselineCreatinineMgDl = baselineCreatinineMgDl;
    in.urineMlKgH = urineMlKgH;
    in.urineDurationHours = urineDurationHours;
    in.anuria = anuria;
    in.evidenceIds.addAll(evidenceIds);
    in.baselineEvidenceIds.addAll(baselineEvidenceIds);
    in.urineEvidenceIds.addAll(urineEvidenceIds);
    return in;
  }
}
