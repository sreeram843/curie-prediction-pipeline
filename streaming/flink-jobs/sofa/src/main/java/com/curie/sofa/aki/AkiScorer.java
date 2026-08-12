package com.curie.sofa.aki;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/**
 * KDIGO-inspired AKI scorer — aligned with {@code eval/aki/scoring.py}.
 * Prototype only — not clinically validated.
 */
public final class AkiScorer {

  private AkiScorer() {}

  public static final class Input implements Serializable {
    public Double creatinineMgDl;
    public Double baselineCreatinineMgDl;
    public Double urineMlKgH;
    public Double urineDurationHours;
    public Boolean anuria;
    public final List<String> evidenceIds = new ArrayList<>();
    public final List<String> baselineEvidenceIds = new ArrayList<>();
    public final List<String> urineEvidenceIds = new ArrayList<>();
  }

  public static final class Result implements Serializable {
    public String patientId;
    public String encounterId;
    public long eventTimeEpochMs;
    public Integer stage;
    public Integer creatinineStage;
    public Integer urineStage;
    public Integer totalScore;
    public String completeness; // complete | partial | insufficient_data
    public final List<String> missingComponents = new ArrayList<>();
    public final List<String> evidenceIds = new ArrayList<>();
    public String ruleBundleId = "aki-kdigo";
    public String ruleVersion = "0.2.0";
  }

  public static int stageToScore(int stage) {
    return switch (stage) {
      case 1 -> 2;
      case 2 -> 4;
      case 3 -> 6;
      default -> 0;
    };
  }

  public static Result compute(
      String patientId, String encounterId, long eventTimeMs, Input in, String version) {
    Result r = new Result();
    r.patientId = patientId;
    r.encounterId = encounterId;
    r.eventTimeEpochMs = eventTimeMs;
    r.ruleVersion = version != null ? version : "0.2.0";
    r.evidenceIds.addAll(in.evidenceIds);
    r.evidenceIds.addAll(in.baselineEvidenceIds);
    r.evidenceIds.addAll(in.urineEvidenceIds);

    Integer uoStage = stageFromUrine(in, r.missingComponents);
    if (in.creatinineMgDl == null && uoStage == null) {
      r.completeness = "insufficient_data";
      r.missingComponents.add("creatinine");
      return r;
    }

    Integer crStage = null;
    if (in.creatinineMgDl != null) {
      crStage = stageFromCreatinine(in.creatinineMgDl, in.baselineCreatinineMgDl, r.missingComponents);
    }
    int stage = 0;
    if (crStage != null) {
      stage = Math.max(stage, crStage);
    }
    if (uoStage != null) {
      stage = Math.max(stage, uoStage);
    }
    r.stage = stage;
    r.creatinineStage = crStage;
    r.urineStage = uoStage;
    r.totalScore = stageToScore(stage);
    r.completeness = r.missingComponents.isEmpty() ? "complete" : "partial";
    return r;
  }

  static int stageFromCreatinine(double cr, Double baseline, List<String> missing) {
    if (baseline == null || baseline <= 0) {
      missing.add("baseline_creatinine");
      return cr >= 4.0 ? 3 : 0;
    }
    double ratio = cr / baseline;
    double delta = cr - baseline;
    if (ratio >= 3.0 || cr >= 4.0) {
      return 3;
    }
    if (ratio >= 2.0) {
      return 2;
    }
    if (ratio >= 1.5 || delta >= 0.3) {
      return 1;
    }
    return 0;
  }

  static Integer stageFromUrine(Input in, List<String> missing) {
    if (Boolean.TRUE.equals(in.anuria) && in.urineDurationHours != null && in.urineDurationHours >= 12) {
      return 3;
    }
    if (in.urineMlKgH == null && in.urineDurationHours == null && in.anuria == null) {
      return null;
    }
    if (in.urineMlKgH == null || in.urineDurationHours == null) {
      missing.add("urine_output");
      return null;
    }
    double rate = in.urineMlKgH;
    double hours = in.urineDurationHours;
    if (rate < 0.3 && hours >= 24) {
      return 3;
    }
    if (rate < 0.5 && hours >= 12) {
      return 2;
    }
    if (rate < 0.5 && hours >= 6) {
      return 1;
    }
    return 0;
  }

  public static String tierForScore(Integer score, int naiveThreshold) {
    if (score == null || score < naiveThreshold) {
      return "none";
    }
    if (score >= 6) {
      return "critical";
    }
    if (score >= 4) {
      return "urgent";
    }
    return "watch";
  }
}
