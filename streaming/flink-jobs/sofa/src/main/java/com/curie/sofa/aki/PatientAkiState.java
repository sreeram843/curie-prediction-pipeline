package com.curie.sofa.aki;

import java.io.Serializable;

/**
 * Encounter-scoped AKI feature state with stateful KDIGO histories (CURIE-009).
 *
 * <p>Legacy single-value fields remain populated for callers that still use {@link
 * #toInput()} / {@link AkiScorer}; new code should prefer {@link #evaluate(long)}.
 */
public class PatientAkiState implements Serializable {
  public String patientId;
  public String encounterId;
  public final AkiTimeline.State timeline = new AkiTimeline.State();

  /** @deprecated Prefer timeline histories via {@link #evaluate(long)}. */
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
    timeline.patientId = patientId;
    timeline.resetForEncounter(encounterId);
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
    AkiTimeline.CrObs obs = new AkiTimeline.CrObs();
    obs.eventTimeMs = eventTimeMs;
    obs.valueMgDl = value;
    obs.evidenceId = evidenceId;
    obs.status = "final";
    timeline.patientId = patientId;
    timeline.encounterId = encounterId;
    timeline.ingestCreatinine(obs);

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
      // Still accepted into timeline (OOO); legacy "current" only advances forward.
      return true;
    }
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
    AkiTimeline.UoObs obs = new AkiTimeline.UoObs();
    obs.endTimeMs = eventTimeMs;
    obs.evidenceId = evidenceId;
    obs.mlKgH = mlKgH;
    obs.durationHours = durationHours;
    obs.anuria = Boolean.TRUE.equals(anuriaFlag);
    timeline.ingestUrine(obs);

    if (urineEventTimeMs != Long.MIN_VALUE && eventTimeMs < urineEventTimeMs) {
      return true;
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

  public boolean applyUrineVolume(
      double volumeMl, double durationHours, long eventTimeMs, String evidenceId) {
    AkiTimeline.UoObs obs = new AkiTimeline.UoObs();
    obs.endTimeMs = eventTimeMs;
    obs.evidenceId = evidenceId;
    obs.volumeMl = volumeMl;
    obs.durationHours = durationHours;
    timeline.ingestUrine(obs);
    return true;
  }

  public boolean applyWeight(double weightKg, long eventTimeMs, String evidenceId) {
    AkiTimeline.WeightObs obs = new AkiTimeline.WeightObs();
    obs.eventTimeMs = eventTimeMs;
    obs.weightKg = weightKg;
    obs.evidenceId = evidenceId;
    timeline.ingestWeight(obs);
    return true;
  }

  public void setFlag(String flag, boolean present) {
    if (present) {
      timeline.flags.add(flag);
    } else {
      timeline.flags.remove(flag);
    }
  }

  public AkiTimeline.Result evaluate(long asOfMs) {
    timeline.patientId = patientId;
    timeline.encounterId = encounterId;
    return AkiTimeline.evaluate(timeline, asOfMs);
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
