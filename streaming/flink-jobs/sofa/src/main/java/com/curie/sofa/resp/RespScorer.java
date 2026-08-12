package com.curie.sofa.resp;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/**
 * Hypoxemic / ventilatory deterioration scorer — aligned with {@code
 * eval/respiratory/scoring.py} (CURIE-013). Prototype only — not clinically
 * validated. SpO2 alone never assumes ambient FiO2 unless {@code roomAir} is
 * true.
 */
public final class RespScorer {

  private RespScorer() {}

  public static final class Input implements Serializable {
    public Double spo2Percent;
    public Double pao2Mmhg;
    public Double fio2Fraction;
    public Double pao2Fio2;
    public Double spo2Fio2;
    public Boolean roomAir;
    public Double respiratoryRate;
    public String oxygenDevice;
    public Boolean mechanicallyVentilated;
    public Double abgPh;
    public Double paco2Mmhg;
    public final List<String> evidenceIds = new ArrayList<>();
  }

  public static final class Result implements Serializable {
    public String patientId;
    public String encounterId;
    public long eventTimeEpochMs;
    public Integer stage;
    public Integer totalScore;
    public String completeness; // complete | partial | insufficient_data
    public final List<String> missingComponents = new ArrayList<>();
    public final List<String> criteriaMet = new ArrayList<>();
    public final List<String> evidenceIds = new ArrayList<>();
    public String ruleBundleId = "resp-deterioration";
    public String ruleVersion = "0.1.0";
    public Double ratioUsed;
    public String ratioSource;
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

    Double[] ratio = effectiveRatio(in);
    r.ratioUsed = ratio[0] != null ? (Double) ratio[0] : null;
    r.ratioSource = ratio[1] != null ? String.valueOf(ratio[1]) : null;

    Integer ox = stageOxygenation(in, r);
    Integer rr = stageRate(in.respiratoryRate, r);
    Integer support = stageSupport(in, r);
    Integer gas = stageBloodGas(in, r);

    int stage = -1;
    if (ox != null) stage = Math.max(stage, ox);
    if (rr != null) stage = Math.max(stage, rr);
    if (support != null) stage = Math.max(stage, support);
    if (gas != null) stage = Math.max(stage, gas);

    if (stage < 0) {
      r.completeness = "insufficient_data";
      if (r.missingComponents.isEmpty()) {
        r.missingComponents.add("oxygenation");
        r.missingComponents.add("respiratory_rate");
        r.missingComponents.add("oxygen_support");
      }
      return r;
    }

    r.stage = stage;
    r.totalScore = stageToScore(stage);
    r.completeness = r.missingComponents.isEmpty() ? "complete" : "partial";
    return r;
  }

  static Double[] effectiveRatio(Input in) {
    if (in.pao2Fio2 != null) {
      return new Double[] {in.pao2Fio2, null};
    }
    // ratioSource carried separately — use Object pair via String in caller
    if (in.spo2Fio2 != null) {
      return new Double[] {in.spo2Fio2, null};
    }
    Double fio2 = in.fio2Fraction;
    if (fio2 == null && Boolean.TRUE.equals(in.roomAir)) {
      fio2 = 0.21;
    }
    if (fio2 == null || fio2 <= 0) {
      return new Double[] {null, null};
    }
    if (in.pao2Mmhg != null) {
      return new Double[] {in.pao2Mmhg / fio2, null};
    }
    if (in.spo2Percent != null) {
      return new Double[] {in.spo2Percent / fio2, null};
    }
    return new Double[] {null, null};
  }

  static Integer stageOxygenation(Input in, Result r) {
    Double[] pair = effectiveRatio(in);
    Double ratio = pair[0];
    if (ratio == null) {
      if (in.spo2Percent != null || in.pao2Mmhg != null) {
        r.missingComponents.add("oxygenation");
      }
      return null;
    }
    String source =
        in.pao2Fio2 != null
            ? "pao2_fio2"
            : in.spo2Fio2 != null
                ? "spo2_fio2"
                : in.pao2Mmhg != null ? "pao2_mmhg/fio2" : "spo2_percent/fio2";
    r.ratioSource = source;
    if (ratio < 100) {
      r.criteriaMet.add("ratio_lt_100:" + source);
      return 3;
    }
    if (ratio < 200) {
      r.criteriaMet.add("ratio_lt_200:" + source);
      return Boolean.TRUE.equals(in.mechanicallyVentilated) ? 3 : 2;
    }
    if (ratio < 300) {
      r.criteriaMet.add("ratio_lt_300:" + source);
      return 2;
    }
    if (ratio < 400) {
      r.criteriaMet.add("ratio_lt_400:" + source);
      return 1;
    }
    r.criteriaMet.add("ratio_ok:" + source);
    return 0;
  }

  static Integer stageRate(Double rr, Result r) {
    if (rr == null) {
      return null;
    }
    if (rr >= 35) {
      r.criteriaMet.add("rr_ge_35");
      return 3;
    }
    if (rr >= 30) {
      r.criteriaMet.add("rr_ge_30");
      return 2;
    }
    if (rr >= 22) {
      r.criteriaMet.add("rr_ge_22");
      return 1;
    }
    r.criteriaMet.add("rr_ok");
    return 0;
  }

  static Integer stageSupport(Input in, Result r) {
    if (Boolean.TRUE.equals(in.mechanicallyVentilated)) {
      r.criteriaMet.add("mechanically_ventilated");
      return 3;
    }
    if (in.oxygenDevice == null) {
      return null;
    }
    String device = in.oxygenDevice.trim().toLowerCase();
    int stage =
        switch (device) {
          case "none" -> 0;
          case "nasal_cannula", "face_mask" -> 1;
          case "high_flow", "non_invasive" -> 2;
          case "invasive" -> 3;
          default -> -1;
        };
    if (stage < 0) {
      r.missingComponents.add("oxygen_support");
      return null;
    }
    if (stage > 0) {
      r.criteriaMet.add("oxygen_device:" + device);
    }
    return stage;
  }

  static Integer stageBloodGas(Input in, Result r) {
    if (in.abgPh == null && in.paco2Mmhg == null) {
      return null;
    }
    int stage = 0;
    if (in.abgPh != null) {
      if (in.abgPh < 7.20) {
        stage = Math.max(stage, 3);
        r.criteriaMet.add("ph_lt_7_20");
      } else if (in.abgPh < 7.25) {
        stage = Math.max(stage, 2);
        r.criteriaMet.add("ph_lt_7_25");
      } else if (in.abgPh < 7.30) {
        stage = Math.max(stage, 1);
        r.criteriaMet.add("ph_lt_7_30");
      }
    }
    if (in.paco2Mmhg != null) {
      if (in.paco2Mmhg > 60) {
        stage = Math.max(stage, 2);
        r.criteriaMet.add("paco2_gt_60");
      } else if (in.paco2Mmhg > 50) {
        stage = Math.max(stage, 1);
        r.criteriaMet.add("paco2_gt_50");
      }
    }
    if (r.criteriaMet.stream().noneMatch(c -> c.startsWith("ph_") || c.startsWith("paco2_"))) {
      r.criteriaMet.add("abg_ok");
    }
    return stage;
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
