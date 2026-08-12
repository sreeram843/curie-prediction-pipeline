package com.curie.sofa.aki;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Stateful KDIGO timeline (CURIE-009) — aligned with {@code eval/aki/timeline.py}.
 * Prototype only — not clinically validated.
 */
public final class AkiTimeline {

  public static final String TIMELINE_VERSION = "1.0.0";
  public static final long MS_48H = 48L * 3600_000L;
  public static final long MS_7D = 7L * 24L * 3600_000L;

  private AkiTimeline() {}

  public static final class CrObs implements Serializable {
    public long eventTimeMs;
    public double valueMgDl;
    public String evidenceId;
    public String status = "final";
  }

  public static final class UoObs implements Serializable {
    public long endTimeMs;
    public String evidenceId;
    public Double volumeMl;
    public Double durationHours;
    public Double mlKgH;
    public boolean anuria;
  }

  public static final class WeightObs implements Serializable {
    public long eventTimeMs;
    public double weightKg;
    public String evidenceId;
  }

  public static final class State implements Serializable {
    public String patientId;
    public String encounterId;
    public final List<CrObs> creatinine = new ArrayList<>();
    public final List<UoObs> urine = new ArrayList<>();
    public final List<WeightObs> weights = new ArrayList<>();
    public final Set<String> flags = new LinkedHashSet<>();

    public void resetForEncounter(String encounterId) {
      this.encounterId = encounterId;
      creatinine.clear();
      urine.clear();
      weights.clear();
      flags.clear();
    }

    public void ingestCreatinine(CrObs obs) {
      String status = obs.status == null ? "final" : obs.status.toLowerCase(Locale.ROOT);
      if (status.equals("entered-in-error")
          || status.equals("cancelled")
          || status.equals("unknown")) {
        return;
      }
      creatinine.removeIf(c -> c.evidenceId != null && c.evidenceId.equals(obs.evidenceId));
      creatinine.add(obs);
      creatinine.sort(
          Comparator.comparingLong((CrObs c) -> c.eventTimeMs)
              .thenComparing(c -> c.evidenceId == null ? "" : c.evidenceId));
    }

    public void ingestUrine(UoObs obs) {
      urine.removeIf(u -> u.evidenceId != null && u.evidenceId.equals(obs.evidenceId));
      urine.add(obs);
      urine.sort(
          Comparator.comparingLong((UoObs u) -> u.endTimeMs)
              .thenComparing(u -> u.evidenceId == null ? "" : u.evidenceId));
    }

    public void ingestWeight(WeightObs obs) {
      if (obs.weightKg <= 0) {
        return;
      }
      weights.removeIf(w -> w.evidenceId != null && w.evidenceId.equals(obs.evidenceId));
      weights.add(obs);
      weights.sort(
          Comparator.comparingLong((WeightObs w) -> w.eventTimeMs)
              .thenComparing(w -> w.evidenceId == null ? "" : w.evidenceId));
    }
  }

  public static final class Result implements Serializable {
    public Integer stage;
    public Integer creatinineStage;
    public Integer urineStage;
    public Integer totalScore;
    public String completeness;
    public String status = "scored";
    public final List<String> missingComponents = new ArrayList<>();
    public final List<String> criteriaMet = new ArrayList<>();
    public final List<String> evidenceIds = new ArrayList<>();
    public Double baseline7dMgDl;
    public Double reference48hMgDl;
    public Double weightKg;
  }

  public static Result evaluate(State state, long asOfMs) {
    Result r = new Result();
    if (state.flags.contains("esrd") && !state.flags.contains("rrt_initiated")) {
      r.status = "excluded";
      r.completeness = "insufficient_data";
      r.missingComponents.add("esrd_exclusion");
      r.criteriaMet.add("exclusion_esrd");
      return r;
    }

    List<CrObs> crHist = new ArrayList<>();
    for (CrObs c : state.creatinine) {
      if (c.eventTimeMs <= asOfMs && c.valueMgDl > 0) {
        crHist.add(c);
      }
    }

    CrObs currentObs = crHist.isEmpty() ? null : crHist.get(crHist.size() - 1);
    Double current = currentObs == null ? null : currentObs.valueMgDl;

    CrObs baselineObs = minInWindow(crHist, asOfMs - MS_7D, asOfMs);
    if (currentObs != null && crHist.size() > 1) {
      List<CrObs> older = new ArrayList<>();
      for (CrObs c : crHist) {
        if (!currentObs.evidenceId.equals(c.evidenceId)) {
          older.add(c);
        }
      }
      CrObs alt = minInWindow(older, asOfMs - MS_7D, asOfMs);
      if (alt != null) {
        baselineObs = alt;
      }
    }
    CrObs ref48 = minInWindow(crHist, asOfMs - MS_48H, asOfMs);
    r.baseline7dMgDl = baselineObs == null ? null : baselineObs.valueMgDl;
    r.reference48hMgDl = ref48 == null ? null : ref48.valueMgDl;

    WeightObs weightObs = latestWeight(state.weights, asOfMs);
    r.weightKg = weightObs == null ? null : weightObs.weightKg;

    RateResult rate6 = meanRate(state.urine, asOfMs, 6, r.weightKg);
    RateResult rate12 = meanRate(state.urine, asOfMs, 12, r.weightKg);
    RateResult rate24 = meanRate(state.urine, asOfMs, 24, r.weightKg);
    AnuriaResult anuria = anuriaHours(state.urine, asOfMs);

    Integer uoStage = null;
    if (anuria.hours >= 12) {
      uoStage = 3;
      r.criteriaMet.add("anuria_ge_12h");
    } else if (rate24.rate != null && rate24.rate < 0.3) {
      uoStage = 3;
      r.criteriaMet.add("uo_lt_0_3_for_24h");
    } else if (rate12.rate != null && rate12.rate < 0.5) {
      uoStage = 2;
      r.criteriaMet.add("uo_lt_0_5_for_12h");
    } else if (rate6.rate != null && rate6.rate < 0.5) {
      uoStage = 1;
      r.criteriaMet.add("uo_lt_0_5_for_6h");
    } else if (rate6.rate != null || rate12.rate != null || rate24.rate != null) {
      uoStage = 0;
    }
    addMissing(r, rate6);
    addMissing(r, rate12);
    addMissing(r, rate24);

    Integer crStage = null;
    if (current != null) {
      crStage = stageFromCreatinine(current, r.baseline7dMgDl, r.reference48hMgDl, r);
      if (currentObs != null) {
        r.evidenceIds.add(currentObs.evidenceId);
      }
      if (baselineObs != null) {
        r.evidenceIds.add(baselineObs.evidenceId);
      }
      if (ref48 != null) {
        r.evidenceIds.add(ref48.evidenceId);
      }
    }
    r.evidenceIds.addAll(rate6.evidence);
    r.evidenceIds.addAll(rate12.evidence);
    r.evidenceIds.addAll(rate24.evidence);
    r.evidenceIds.addAll(anuria.evidence);

    if (state.flags.contains("rrt_initiated")) {
      r.criteriaMet.add("rrt");
    }

    if (current == null && uoStage == null && !state.flags.contains("rrt_initiated")) {
      r.status = "insufficient_data";
      r.completeness = "insufficient_data";
      if (!r.missingComponents.contains("creatinine")) {
        r.missingComponents.add(0, "creatinine");
      }
      return r;
    }

    int stage = 0;
    if (crStage != null) {
      stage = Math.max(stage, crStage);
    }
    if (uoStage != null) {
      stage = Math.max(stage, uoStage);
    }
    if (state.flags.contains("rrt_initiated")) {
      stage = Math.max(stage, 3);
    }
    r.stage = stage;
    r.creatinineStage = crStage;
    r.urineStage = uoStage;
    r.totalScore = AkiScorer.stageToScore(stage);
    r.completeness = r.missingComponents.isEmpty() ? "complete" : "partial";
    // de-dupe evidence
    r.evidenceIds.clear();
    LinkedHashSet<String> uniq = new LinkedHashSet<>();
    if (currentObs != null) {
      uniq.add(currentObs.evidenceId);
    }
    if (baselineObs != null) {
      uniq.add(baselineObs.evidenceId);
    }
    if (ref48 != null) {
      uniq.add(ref48.evidenceId);
    }
    uniq.addAll(rate6.evidence);
    uniq.addAll(rate12.evidence);
    uniq.addAll(rate24.evidence);
    uniq.addAll(anuria.evidence);
    r.evidenceIds.addAll(uniq);
    return r;
  }

  private static void addMissing(Result r, RateResult rate) {
    for (String m : rate.missing) {
      if (!r.missingComponents.contains(m)) {
        r.missingComponents.add(m);
      }
    }
  }

  private static int stageFromCreatinine(
      double current, Double baseline7d, Double ref48, Result r) {
    int stage = 0;
    if (baseline7d == null || baseline7d <= 0) {
      r.missingComponents.add("baseline_creatinine");
      if (current >= 4.0) {
        r.criteriaMet.add("cr_ge_4_0");
        return 3;
      }
      return 0;
    }
    double ratio = current / baseline7d;
    if (current >= 4.0) {
      stage = 3;
      r.criteriaMet.add("cr_ge_4_0");
    }
    if (ratio >= 3.0) {
      stage = 3;
      r.criteriaMet.add("cr_ge_3_0x_baseline");
    } else if (ratio >= 2.0) {
      stage = Math.max(stage, 2);
      r.criteriaMet.add("cr_ge_2_0x_baseline");
    } else if (ratio >= 1.5) {
      stage = Math.max(stage, 1);
      r.criteriaMet.add("cr_ge_1_5x_baseline");
    }
    if (ref48 != null && current - ref48 >= 0.3) {
      stage = Math.max(stage, 1);
      r.criteriaMet.add("delta_cr_ge_0_3_within_48h");
    }
    return stage;
  }

  private static CrObs minInWindow(List<CrObs> obs, long startMs, long endMs) {
    CrObs best = null;
    for (CrObs c : obs) {
      if (c.eventTimeMs < startMs || c.eventTimeMs > endMs) {
        continue;
      }
      if (best == null
          || c.valueMgDl < best.valueMgDl
          || (c.valueMgDl == best.valueMgDl && c.eventTimeMs < best.eventTimeMs)) {
        best = c;
      }
    }
    return best;
  }

  private static WeightObs latestWeight(List<WeightObs> weights, long asOfMs) {
    WeightObs best = null;
    for (WeightObs w : weights) {
      if (w.eventTimeMs > asOfMs || w.weightKg <= 0) {
        continue;
      }
      if (best == null || w.eventTimeMs > best.eventTimeMs) {
        best = w;
      }
    }
    return best;
  }

  private static final class RateResult {
    Double rate;
    final List<String> evidence = new ArrayList<>();
    final List<String> missing = new ArrayList<>();
  }

  private static final class AnuriaResult {
    double hours;
    final List<String> evidence = new ArrayList<>();
  }

  private static RateResult meanRate(
      List<UoObs> urine, long asOfMs, double windowHours, Double weightKg) {
    RateResult out = new RateResult();
    long startMs = asOfMs - (long) (windowHours * 3600_000L);
    List<UoObs> segments = new ArrayList<>();
    for (UoObs u : urine) {
      if (u.endTimeMs > startMs && u.endTimeMs <= asOfMs) {
        segments.add(u);
      }
    }
    if (segments.isEmpty()) {
      return out;
    }

    boolean hasLegacy = false;
    boolean hasVolume = false;
    for (UoObs u : segments) {
      if (u.mlKgH != null && u.durationHours != null) {
        hasLegacy = true;
      }
      if (u.volumeMl != null) {
        hasVolume = true;
      }
    }

    if (hasLegacy && !hasVolume) {
      double totalH = 0;
      double weighted = 0;
      for (UoObs u : segments) {
        if (u.mlKgH == null || u.durationHours == null) {
          continue;
        }
        long segStart = u.endTimeMs - (long) (u.durationHours * 3600_000L);
        long overlapStart = Math.max(segStart, startMs);
        double overlapH = (u.endTimeMs - overlapStart) / 3600_000.0;
        if (overlapH <= 0) {
          continue;
        }
        weighted += u.mlKgH * overlapH;
        totalH += overlapH;
        out.evidence.add(u.evidenceId);
      }
      if (totalH + 1e-9 < windowHours) {
        return out;
      }
      out.rate = weighted / totalH;
      return out;
    }

    if (hasVolume) {
      if (weightKg == null || weightKg <= 0) {
        out.missing.add("weight_kg");
        return out;
      }
      double totalMl = 0;
      double coveredH = 0;
      for (UoObs u : segments) {
        if (u.volumeMl == null || u.durationHours == null || u.durationHours <= 0) {
          continue;
        }
        long segStart = u.endTimeMs - (long) (u.durationHours * 3600_000L);
        long overlapStart = Math.max(segStart, startMs);
        if (u.endTimeMs <= overlapStart) {
          continue;
        }
        double overlapH = (u.endTimeMs - overlapStart) / 3600_000.0;
        double frac = overlapH / u.durationHours;
        totalMl += u.volumeMl * Math.max(0.0, Math.min(1.0, frac));
        coveredH += overlapH;
        out.evidence.add(u.evidenceId);
      }
      if (coveredH + 1e-9 < windowHours) {
        return out;
      }
      out.rate = totalMl / (weightKg * coveredH);
      return out;
    }
    return out;
  }

  private static AnuriaResult anuriaHours(List<UoObs> urine, long asOfMs) {
    AnuriaResult out = new AnuriaResult();
    long floor = asOfMs - MS_48H;
    for (UoObs u : urine) {
      if (!u.anuria || u.endTimeMs > asOfMs || u.endTimeMs < floor) {
        continue;
      }
      out.hours += u.durationHours == null ? 0.0 : u.durationHours;
      out.evidence.add(u.evidenceId);
    }
    return out;
  }
}
