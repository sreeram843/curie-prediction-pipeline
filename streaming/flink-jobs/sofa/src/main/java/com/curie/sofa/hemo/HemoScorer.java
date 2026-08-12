package com.curie.sofa.hemo;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/**
 * Hemodynamic shock / hyperlactatemia surveillance scorer — aligned with {@code
 * eval/hemodynamic/scoring.py} (CURIE-036). Prototype only — not a clinical diagnosis.
 */
public final class HemoScorer {

  private HemoScorer() {}

  public static final class Input implements Serializable {
    public Double lactateMmolL;
    public Double mapMmhg;
    public Boolean onVasopressor;
    public final List<String> evidenceIds = new ArrayList<>();
  }

  public static final class Result implements Serializable {
    public String patientId;
    public String encounterId;
    public long eventTimeEpochMs;
    public Integer stage;
    public Integer totalScore;
    public String completeness;
    public final List<String> missingComponents = new ArrayList<>();
    public final List<String> criteriaMet = new ArrayList<>();
    public final List<String> evidenceIds = new ArrayList<>();
    public String ruleBundleId = "hemo-shock";
    public String ruleVersion = "0.1.0";
    public String clinicalClaim = "surveillance_indicator_not_diagnosis";
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
    r.ruleVersion = version != null ? version : "0.1.0";
    r.evidenceIds.addAll(in.evidenceIds);

    Integer lac = stageLactate(in.lactateMmolL, r);
    Integer map = stageMap(in.mapMmhg, r);
    Integer vaso = stageVaso(in.onVasopressor, r);

    int stage = -1;
    if (lac != null) stage = Math.max(stage, lac);
    if (map != null) stage = Math.max(stage, map);
    if (vaso != null) stage = Math.max(stage, vaso);

    if (stage < 0) {
      r.completeness = "insufficient_data";
      if (r.missingComponents.isEmpty()) {
        r.missingComponents.add("lactate");
        r.missingComponents.add("mean_arterial_pressure");
      }
      return r;
    }
    r.stage = stage;
    r.totalScore = stageToScore(stage);
    r.completeness = r.missingComponents.isEmpty() ? "complete" : "partial";
    return r;
  }

  static Integer stageLactate(Double v, Result r) {
    if (v == null) {
      r.missingComponents.add("lactate");
      return null;
    }
    if (v >= 4.0) {
      r.criteriaMet.add("lactate_ge_4");
      return 3;
    }
    if (v >= 2.0) {
      r.criteriaMet.add("lactate_ge_2");
      return 2;
    }
    if (v >= 1.5) {
      r.criteriaMet.add("lactate_ge_1_5");
      return 1;
    }
    r.criteriaMet.add("lactate_ok");
    return 0;
  }

  static Integer stageMap(Double v, Result r) {
    if (v == null) {
      r.missingComponents.add("mean_arterial_pressure");
      return null;
    }
    if (v < 55) {
      r.criteriaMet.add("map_lt_55");
      return 3;
    }
    if (v < 65) {
      r.criteriaMet.add("map_lt_65");
      return 2;
    }
    if (v < 70) {
      r.criteriaMet.add("map_lt_70");
      return 1;
    }
    r.criteriaMet.add("map_ok");
    return 0;
  }

  static Integer stageVaso(Boolean on, Result r) {
    if (on == null) {
      return null;
    }
    if (Boolean.TRUE.equals(on)) {
      r.criteriaMet.add("on_vasopressor");
      return 2;
    }
    r.criteriaMet.add("vaso_off");
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
