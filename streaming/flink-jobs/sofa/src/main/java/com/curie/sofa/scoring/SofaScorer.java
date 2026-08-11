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

  public static final class ComponentInput {
    public Component name;
    public Double pao2Fio2;
    public Double spo2Fio2;
    public Boolean mechanicallyVentilated;
    public Double platelets10e9L;
    public Double bilirubinMgDl;
    public Double mapMmhg;
    public Boolean onVasopressors;
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
    Double ratio = in.pao2Fio2 != null ? in.pao2Fio2 : in.spo2Fio2;
    if (ratio == null) {
      return null;
    }
    boolean vent = Boolean.TRUE.equals(in.mechanicallyVentilated);
    if (ratio < 100 && vent) {
      return 4;
    }
    if (ratio < 200 && vent) {
      return 3;
    }
    if (ratio < 300) {
      return 2;
    }
    if (ratio < 400) {
      return 1;
    }
    return 0;
  }

  public static Integer scoreCoagulation(ComponentInput in) {
    if (in.platelets10e9L == null) {
      return null;
    }
    double p = in.platelets10e9L;
    if (p < 20) {
      return 4;
    }
    if (p < 50) {
      return 3;
    }
    if (p < 100) {
      return 2;
    }
    if (p < 150) {
      return 1;
    }
    return 0;
  }

  public static Integer scoreLiver(ComponentInput in) {
    if (in.bilirubinMgDl == null) {
      return null;
    }
    double b = in.bilirubinMgDl;
    if (b >= 12.0) {
      return 4;
    }
    if (b >= 6.0) {
      return 3;
    }
    if (b >= 2.0) {
      return 2;
    }
    if (b >= 1.2) {
      return 1;
    }
    return 0;
  }

  public static Integer scoreCardiovascular(ComponentInput in) {
    if (Boolean.TRUE.equals(in.onVasopressors)) {
      return 3;
    }
    if (in.mapMmhg == null && in.onVasopressors == null) {
      return null;
    }
    if (in.mapMmhg != null && in.mapMmhg < 70) {
      return 1;
    }
    if (in.mapMmhg != null) {
      return 0;
    }
    return null;
  }

  public static Integer scoreCns(ComponentInput in) {
    if (in.gcs == null) {
      return null;
    }
    int g = in.gcs;
    if (g < 6) {
      return 4;
    }
    if (g <= 9) {
      return 3;
    }
    if (g <= 12) {
      return 2;
    }
    if (g <= 14) {
      return 1;
    }
    return 0;
  }

  public static Integer scoreRenal(ComponentInput in) {
    List<Integer> points = new ArrayList<>();
    if (in.creatinineMgDl != null) {
      double c = in.creatinineMgDl;
      if (c >= 5.0) {
        points.add(4);
      } else if (c >= 3.5) {
        points.add(3);
      } else if (c >= 2.0) {
        points.add(2);
      } else if (c >= 1.2) {
        points.add(1);
      } else {
        points.add(0);
      }
    }
    if (in.urineOutputMlDay != null) {
      double u = in.urineOutputMlDay;
      if (u < 200) {
        points.add(4);
      } else if (u < 500) {
        points.add(3);
      } else {
        points.add(0);
      }
    }
    if (points.isEmpty()) {
      return null;
    }
    return points.stream().mapToInt(Integer::intValue).max().orElseThrow();
  }

  private static Integer scoreComponent(ComponentInput in) {
    return switch (in.name) {
      case RESPIRATION -> scoreRespiration(in);
      case COAGULATION -> scoreCoagulation(in);
      case LIVER -> scoreLiver(in);
      case CARDIOVASCULAR -> scoreCardiovascular(in);
      case CNS -> scoreCns(in);
      case RENAL -> scoreRenal(in);
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
    Map<Component, ComponentInput> byName = new EnumMap<>(Component.class);
    for (ComponentInput in : inputs) {
      byName.put(in.name, in);
    }

    List<ComponentScore> components = new ArrayList<>();
    List<String> evidence = new ArrayList<>();
    for (Component name : Component.values()) {
      ComponentInput in = byName.getOrDefault(name, new ComponentInput(name));
      Integer points = scoreComponent(in);
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
    if (score == null || score < naiveThreshold) {
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
