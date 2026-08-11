package com.curie.governance;

import java.io.Serializable;
import java.time.Instant;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Indicator-agnostic alert governance decisions. Pure logic shared by Flink operators and eval
 * harnesses. Does not depend on the SOFA module (avoids Maven cycles).
 */
public final class GovernancePolicy {

  public static final class Config implements Serializable {
    public long trajectoryPersistenceMs = 30L * 60L * 1000L;
    public int minCrossings = 2;
    public boolean baselineEnabled = true;
    public long baselineLookbackMs = 24L * 60L * 60L * 1000L;
    public int baselineDeltaThreshold = 2;
    public long refractoryMs = 120L * 60L * 1000L;
    public Set<String> suppressionFlags =
        new HashSet<>(Set.of("comfort_care", "already_on_sepsis_protocol"));
    public Set<String> interruptiveTiers = new HashSet<>(Set.of("urgent", "critical"));
    public Set<String> passiveTiers = new HashSet<>(Set.of("watch"));
  }

  public static final class PatientGovState implements Serializable {
    public Integer lastEmittedScore;
    public long lastEmittedEventTimeMs = Long.MIN_VALUE;
    public int crossingsAboveThreshold;
    public long firstCrossingEventTimeMs = Long.MIN_VALUE;
    public Integer baselineScore;
    public final Set<String> contextFlags = new HashSet<>();
  }

  /** Minimal alert view mutated in place by governance. */
  public static final class AlertView implements Serializable {
    public Integer score;
    public String tier;
    public String eventTime;
    public String governancePath = "naive";
    public boolean suppressed;
    public String suppressionReason;
  }

  public static final class Decision implements Serializable {
    public final boolean emit;
    public final boolean suppressed;
    public final String reason;
    public final String routing;
    public final AlertView alert;

    public Decision(
        boolean emit, boolean suppressed, String reason, String routing, AlertView alert) {
      this.emit = emit;
      this.suppressed = suppressed;
      this.reason = reason;
      this.routing = routing;
      this.alert = alert;
    }
  }

  private GovernancePolicy() {}

  public static Decision evaluate(AlertView naive, PatientGovState state, Config config) {
    if (naive == null || naive.score == null) {
      return new Decision(false, true, "no_score", "none", naive);
    }
    long eventTimeMs = parseMs(naive.eventTime);

    for (String flag : state.contextFlags) {
      if (config.suppressionFlags.contains(flag)) {
        naive.suppressed = true;
        naive.suppressionReason = "context:" + flag;
        naive.governancePath = "governed";
        return new Decision(false, true, naive.suppressionReason, "none", naive);
      }
    }

    if (state.firstCrossingEventTimeMs == Long.MIN_VALUE) {
      state.firstCrossingEventTimeMs = eventTimeMs;
      state.crossingsAboveThreshold = 1;
    } else {
      state.crossingsAboveThreshold += 1;
    }
    long persisted = eventTimeMs - state.firstCrossingEventTimeMs;
    if (state.crossingsAboveThreshold < config.minCrossings
        || persisted < config.trajectoryPersistenceMs) {
      naive.suppressed = true;
      naive.suppressionReason = "trajectory_not_met";
      naive.governancePath = "governed";
      return new Decision(false, true, "trajectory_not_met", "none", naive);
    }

    if (config.baselineEnabled && state.baselineScore != null) {
      int delta = naive.score - state.baselineScore;
      if (delta < config.baselineDeltaThreshold) {
        naive.suppressed = true;
        naive.suppressionReason = "below_baseline_delta";
        naive.governancePath = "governed";
        return new Decision(false, true, "below_baseline_delta", "none", naive);
      }
    } else if (config.baselineEnabled && state.baselineScore == null) {
      state.baselineScore = naive.score;
      naive.suppressed = true;
      naive.suppressionReason = "baseline_init";
      naive.governancePath = "governed";
      return new Decision(false, true, "baseline_init", "none", naive);
    }

    if (state.lastEmittedEventTimeMs != Long.MIN_VALUE
        && eventTimeMs - state.lastEmittedEventTimeMs < config.refractoryMs) {
      naive.suppressed = true;
      naive.suppressionReason = "refractory";
      naive.governancePath = "governed";
      return new Decision(false, true, "refractory", "none", naive);
    }

    String tier = naive.tier == null ? "none" : naive.tier.toLowerCase(Locale.ROOT);
    String routing;
    if (config.interruptiveTiers.contains(tier)) {
      routing = "interruptive";
    } else if (config.passiveTiers.contains(tier)) {
      routing = "passive";
    } else {
      routing = "none";
    }

    naive.suppressed = false;
    naive.suppressionReason = null;
    naive.governancePath = "governed";
    state.lastEmittedEventTimeMs = eventTimeMs;
    state.lastEmittedScore = naive.score;
    return new Decision(true, false, "pass", routing, naive);
  }

  private static long parseMs(String iso) {
    if (iso == null || iso.isBlank()) {
      return Instant.EPOCH.toEpochMilli();
    }
    return Instant.parse(iso.replace(" ", "T")).toEpochMilli();
  }
}
