package com.curie.sofa.scoring;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * Deterministic SOFA-style scorer. Must stay aligned with {@code eval/sofa/scoring.py}.
 * Prototype only — not clinically validated. Missing components are never imputed.
 */
public final class SofaScorer {

  public enum Component {
    RESPIRATION("respiration"),
    COAGULATION("coagulation"),
    LIVER("liver"),
    CARDIOVASCULAR("cardiovascular"),
    CNS("cns"),
    RENAL("renal");

    private final String wireName;

    Component(String wireName) {
      this.wireName = wireName;
    }

    public String wireName() {
      return wireName;
    }

    public static Component fromWire(String name) {
      for (Component c : values()) {
        if (c.wireName.equals(name)) {
          return c;
        }
      }
      throw new IllegalArgumentException("Unknown SOFA component: " + name);
    }
  }

  public enum Completeness {
    COMPLETE("complete"),
    PARTIAL("partial"),
    INSUFFICIENT_DATA("insufficient_data");

    private final String wireName;

    Completeness(String wireName) {
      this.wireName = wireName;
    }

    public String wireName() {
      return wireName;
    }
  }

  public enum Tier {
    NONE("none"),
    WATCH("watch"),
    URGENT("urgent"),
    CRITICAL("critical");

    private final String wireName;

    Tier(String wireName) {
      this.wireName = wireName;
    }

    public String wireName() {
      return wireName;
    }
  }

  public static final class ComponentInput implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    public Component name;
    public Double pao2Fio2;
    public Double spo2Fio2;
    /** Raw SpO2 % — ratio only computed when fio2Fraction is also present. */
    public Double spo2Percent;
    /** Raw PaO2 mmHg — ratio only computed when fio2Fraction is also present. */
    public Double pao2Mmhg;
    /** Inspired O2 as fraction 0–1 (e.g. 0.21–1.0). */
    public Double fio2Fraction;
    public Boolean mechanicallyVentilated;
    public Double platelets10e9L;
    public Double bilirubinMgDl;
    public Double mapMmhg;
    public Boolean onVasopressors;
    /** dopamine | dobutamine | epinephrine | norepinephrine | other */
    public String vasopressorAgent;
    public Double vasopressorDoseUgKgMin;
    public Integer gcs;
    public Double creatinineMgDl;
    public Double urineOutputMlDay;
    public final List<String> evidenceIds = new ArrayList<>();

    public ComponentInput(Component name) {
      this.name = Objects.requireNonNull(name);
    }
  }

  public static final class ComponentScore {
    public final Component name;
    public final Integer points;
    public final boolean missing;
    public final List<String> evidenceIds;

    public ComponentScore(Component name, Integer points, boolean missing, List<String> evidenceIds) {
      this.name = name;
      this.points = points;
      this.missing = missing;
      this.evidenceIds = List.copyOf(evidenceIds);
    }
  }

  public static final class ScoreResult {
    public final String patientId;
    public final String encounterId;
    public final long eventTimeEpochMs;
    public final Integer totalScore;
    public final Completeness completeness;
    public final List<ComponentScore> components;
    public final List<Component> missingComponents;
    public final List<String> evidenceIds;
    public final String ruleBundleId;
    public final String ruleVersion;
    public final int minComponentsRequired;

    public ScoreResult(
        String patientId,
        String encounterId,
        long eventTimeEpochMs,
        Integer totalScore,
        Completeness completeness,
        List<ComponentScore> components,
        List<Component> missingComponents,
        List<String> evidenceIds,
        String ruleBundleId,
        String ruleVersion,
        int minComponentsRequired) {
      this.patientId = patientId;
      this.encounterId = encounterId;
      this.eventTimeEpochMs = eventTimeEpochMs;
      this.totalScore = totalScore;
      this.completeness = completeness;
      this.components = List.copyOf(components);
      this.missingComponents = List.copyOf(missingComponents);
      this.evidenceIds = List.copyOf(evidenceIds);
      this.ruleBundleId = ruleBundleId;
      this.ruleVersion = ruleVersion;
      this.minComponentsRequired = minComponentsRequired;
    }
  }

  private SofaScorer() {}

  public static Integer scoreRespiration(ComponentInput in) {
    return scoreRespiration(in, SofaThresholds.defaults());
  }

  public static Integer scoreRespiration(ComponentInput in, SofaThresholds th) {
    Double ratio = effectiveRatio(in);
    if (ratio == null) {
      return null;
    }
    boolean vent = Boolean.TRUE.equals(in.mechanicallyVentilated);
    if (ratio < th.respP4Lt && vent) {
      return 4;
    }
    if (ratio < th.respP3Lt && vent) {
      return 3;
    }
    if (ratio < th.respP2Lt) {
      return 2;
    }
    if (ratio < th.respP1Lt) {
      return 1;
    }
    return 0;
  }

  /** Prefer explicit ratio fields; else PaO2/FiO2 or SpO2/FiO2 when FiO2 known. Never assumes 0.21. */
  public static Double effectiveRatio(ComponentInput in) {
    if (in.pao2Fio2 != null) {
      return in.pao2Fio2;
    }
    if (in.spo2Fio2 != null) {
      return in.spo2Fio2;
    }
    if (in.fio2Fraction == null || in.fio2Fraction <= 0) {
      return null;
    }
    if (in.pao2Mmhg != null) {
      return in.pao2Mmhg / in.fio2Fraction;
    }
    if (in.spo2Percent != null) {
      return in.spo2Percent / in.fio2Fraction;
    }
    return null;
  }

  public static Integer scoreCoagulation(ComponentInput in) {
    return scoreCoagulation(in, SofaThresholds.defaults());
  }

  public static Integer scoreCoagulation(ComponentInput in, SofaThresholds th) {
    if (in.platelets10e9L == null) {
      return null;
    }
    double p = in.platelets10e9L;
    for (int i = 0; i < th.coagMaxExclusive.length; i++) {
      if (p < th.coagMaxExclusive[i]) {
        return th.coagPoints[i];
      }
    }
    if (p >= th.coagMinInclusiveZero) {
      return 0;
    }
    return 0;
  }

  public static Integer scoreLiver(ComponentInput in) {
    return scoreLiver(in, SofaThresholds.defaults());
  }

  public static Integer scoreLiver(ComponentInput in, SofaThresholds th) {
    if (in.bilirubinMgDl == null) {
      return null;
    }
    double b = in.bilirubinMgDl;
    for (int i = 0; i < th.liverMinInclusive.length; i++) {
      if (b >= th.liverMinInclusive[i]) {
        return th.liverPoints[i];
      }
    }
    return 0;
  }

  public static Integer scoreCardiovascular(ComponentInput in) {
    return scoreCardiovascular(in, SofaThresholds.defaults());
  }

  public static Integer scoreCardiovascular(ComponentInput in, SofaThresholds th) {
    Integer pressor = vasopressorPoints(in, th);
    if (pressor != null) {
      return pressor;
    }
    if (in.mapMmhg == null && in.onVasopressors == null) {
      return null;
    }
    if (in.mapMmhg != null && in.mapMmhg < th.mapLt) {
      return th.mapPoints;
    }
    if (in.mapMmhg != null) {
      return 0;
    }
    return null;
  }

  /**
   * Vincent SOFA cardiovascular ladder. Unknown dose with pressors present → configured default.
   */
  static Integer vasopressorPoints(ComponentInput in) {
    return vasopressorPoints(in, SofaThresholds.defaults());
  }

  static Integer vasopressorPoints(ComponentInput in, SofaThresholds th) {
    String agent = in.vasopressorAgent == null ? null : in.vasopressorAgent.toLowerCase();
    Double dose = in.vasopressorDoseUgKgMin;
    if ("dobutamine".equals(agent)) {
      return 2;
    }
    if ("dopamine".equals(agent) && dose != null) {
      if (dose > th.dopamineP3Max) {
        return 4;
      }
      if (dose > th.dopamineP2Max) {
        return 3;
      }
      return 2;
    }
    if (("epinephrine".equals(agent) || "norepinephrine".equals(agent)) && dose != null) {
      if (dose > th.epiNorepiP3Max) {
        return 4;
      }
      return 3;
    }
    if ("other".equals(agent) && dose != null) {
      return dose <= th.epiNorepiP3Max ? 3 : 4;
    }
    if (Boolean.TRUE.equals(in.onVasopressors) || agent != null) {
      return th.unknownPressorPoints;
    }
    return null;
  }

  public static Integer scoreCns(ComponentInput in) {
    return scoreCns(in, SofaThresholds.defaults());
  }

  public static Integer scoreCns(ComponentInput in, SofaThresholds th) {
    if (in.gcs == null) {
      return null;
    }
    int g = in.gcs;
    if (g < th.cnsLt4) {
      return 4;
    }
    if (g <= th.cnsLe3) {
      return 3;
    }
    if (g <= th.cnsLe2) {
      return 2;
    }
    if (g <= th.cnsLe1) {
      return 1;
    }
    return 0;
  }

  public static Integer scoreRenal(ComponentInput in) {
    return scoreRenal(in, SofaThresholds.defaults());
  }

  public static Integer scoreRenal(ComponentInput in, SofaThresholds th) {
    List<Integer> points = new ArrayList<>();
    if (in.creatinineMgDl != null) {
      double c = in.creatinineMgDl;
      boolean matched = false;
      for (int i = 0; i < th.renalCrMin.length; i++) {
        if (c >= th.renalCrMin[i]) {
          points.add(th.renalCrPoints[i]);
          matched = true;
          break;
        }
      }
      if (!matched) {
        points.add(0);
      }
    }
    if (in.urineOutputMlDay != null) {
      double u = in.urineOutputMlDay;
      boolean matched = false;
      for (int i = 0; i < th.renalUoMax.length; i++) {
        if (u < th.renalUoMax[i]) {
          points.add(th.renalUoPoints[i]);
          matched = true;
          break;
        }
      }
      if (!matched) {
        points.add(0);
      }
    }
    if (points.isEmpty()) {
      return null;
    }
    return points.stream().mapToInt(Integer::intValue).max().orElseThrow();
  }

  private static Integer scoreComponent(ComponentInput in, SofaThresholds th) {
    return switch (in.name) {
      case RESPIRATION -> scoreRespiration(in, th);
      case COAGULATION -> scoreCoagulation(in, th);
      case LIVER -> scoreLiver(in, th);
      case CARDIOVASCULAR -> scoreCardiovascular(in, th);
      case CNS -> scoreCns(in, th);
      case RENAL -> scoreRenal(in, th);
    };
  }

  public static ScoreResult compute(
      String patientId,
      String encounterId,
      long eventTimeEpochMs,
      List<ComponentInput> inputs,
      String ruleBundleId,
      String ruleVersion,
      int minComponentsRequired) {
    return compute(
        patientId,
        encounterId,
        eventTimeEpochMs,
        inputs,
        ruleBundleId,
        ruleVersion,
        minComponentsRequired,
        SofaThresholds.defaults());
  }

  public static ScoreResult compute(
      String patientId,
      String encounterId,
      long eventTimeEpochMs,
      List<ComponentInput> inputs,
      String ruleBundleId,
      String ruleVersion,
      int minComponentsRequired,
      SofaThresholds thresholds) {
    SofaThresholds th = thresholds != null ? thresholds : SofaThresholds.defaults();
    Map<Component, ComponentInput> byName = new EnumMap<>(Component.class);
    for (ComponentInput in : inputs) {
      byName.put(in.name, in);
    }

    List<ComponentScore> components = new ArrayList<>();
    List<String> evidence = new ArrayList<>();
    for (Component name : Component.values()) {
      ComponentInput in = byName.getOrDefault(name, new ComponentInput(name));
      Integer points = scoreComponent(in, th);
      boolean missing = points == null;
      components.add(new ComponentScore(name, points, missing, in.evidenceIds));
      evidence.addAll(in.evidenceIds);
    }

    List<ComponentScore> present = components.stream().filter(c -> !c.missing).toList();
    List<Component> missingNames =
        components.stream().filter(c -> c.missing).map(c -> c.name).toList();

    Completeness completeness;
    Integer total;
    if (present.size() < minComponentsRequired) {
      completeness = Completeness.INSUFFICIENT_DATA;
      total = null;
    } else if (!missingNames.isEmpty()) {
      completeness = Completeness.PARTIAL;
      total = present.stream().mapToInt(c -> c.points).sum();
    } else {
      completeness = Completeness.COMPLETE;
      total = present.stream().mapToInt(c -> c.points).sum();
    }

    Set<String> seen = new LinkedHashSet<>();
    List<String> uniqEvidence = new ArrayList<>();
    for (String e : evidence) {
      if (seen.add(e)) {
        uniqEvidence.add(e);
      }
    }

    return new ScoreResult(
        patientId,
        encounterId,
        eventTimeEpochMs,
        total,
        completeness,
        components,
        missingNames,
        uniqEvidence,
        ruleBundleId,
        ruleVersion,
        minComponentsRequired);
  }

  public static Tier tierForScore(Integer score, int naiveThreshold) {
    return tierForScore(score, naiveThreshold, null);
  }

  /**
   * Prefer explicit severity_bands from the rule bundle when present; otherwise use legacy
   * 2–3 watch / 4–6 urgent / ≥7 critical.
   */
  public static Tier tierForScore(
      Integer score, int naiveThreshold, List<com.curie.sofa.model.RuleBundle.SeverityBand> bands) {
    if (score == null || score < naiveThreshold) {
      return Tier.NONE;
    }
    if (bands != null && !bands.isEmpty()) {
      for (com.curie.sofa.model.RuleBundle.SeverityBand band : bands) {
        if (score >= band.min && score <= band.max) {
          return Tier.valueOf(band.tier.toUpperCase(java.util.Locale.ROOT));
        }
      }
      // Above last band max → use highest matching-ish critical if score high
      com.curie.sofa.model.RuleBundle.SeverityBand last = bands.get(bands.size() - 1);
      if (score > last.max) {
        return Tier.valueOf(last.tier.toUpperCase(java.util.Locale.ROOT));
      }
      return Tier.NONE;
    }
    if (score >= 7) {
      return Tier.CRITICAL;
    }
    if (score >= 4) {
      return Tier.URGENT;
    }
    return Tier.WATCH;
  }
}
