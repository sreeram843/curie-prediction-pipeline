package com.curie.governance;

import java.io.Serializable;
import java.time.Instant;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Indicator-agnostic alert governance decisions. Pure logic shared by Flink operators and eval
 * harnesses. Does not depend on the SOFA module (avoids Maven cycles).
 *
 * <p>Trajectory counts unique event-times only. A gap larger than {@code resolutionGapMs} since the
 * last qualifying observation resets the crossing streak (recovery / re-deterioration). Below-threshold
 * (tier {@code none}) signals call {@link #noteBelowThreshold}. {@code contextFlags} are
 * <strong>encounter-scoped</strong>: they clear when {@code encounterId} changes.
 *
 * <p>Optional dual-lane page gate ({@code pageGateEnabled}): interruptive tiers may be downgraded to
 * passive (watch) when page gates fail, preserving detection while cutting pages.
 */
public final class GovernancePolicy {

  public static final class Config implements Serializable {
    public long trajectoryPersistenceMs = 30L * 60L * 1000L;
    public int minCrossings = 2;
    public boolean baselineEnabled = true;
    public long baselineLookbackMs = 24L * 60L * 60L * 1000L;
    public int baselineDeltaThreshold = 2;
    public long refractoryMs = 120L * 60L * 1000L;
    /** If no qualifying observation for this long, reset trajectory on next alert. */
    public long resolutionGapMs = 60L * 60L * 1000L;
    public Set<String> suppressionFlags =
        new HashSet<>(Set.of("comfort_care", "already_on_sepsis_protocol"));
    public Set<String> interruptiveTiers = new HashSet<>(Set.of("urgent", "critical"));
    public Set<String> passiveTiers = new HashSet<>(Set.of("watch"));
    /** When true, interruptive routing also requires page_* gates (else downgrade to passive). */
    public boolean pageGateEnabled = false;
    public int pageMinCrossings = 2;
    public long pageTrajectoryPersistenceMs = 30L * 60L * 1000L;
    /** Rise vs first crossing score; 0 disables. */
    public int pageMinScoreDelta = 1;
    /** 0 disables; uses {@link AlertView#positiveComponents}. */
    public int pageMinPositiveComponents = 0;

    public static Config fromBundleKnobs(
        int persistenceMinutes,
        int minCrossings,
        boolean baselineEnabled,
        int baselineDelta,
        int lookbackHours,
        int refractoryMinutes,
        int resolutionGapMinutes,
        Set<String> suppressionFlags,
        Set<String> interruptive,
        Set<String> passive) {
      Config c = new Config();
      c.trajectoryPersistenceMs = persistenceMinutes * 60L * 1000L;
      c.minCrossings = minCrossings;
      c.baselineEnabled = baselineEnabled;
      c.baselineDeltaThreshold = baselineDelta;
      c.baselineLookbackMs = Math.max(1, lookbackHours) * 60L * 60L * 1000L;
      c.refractoryMs = refractoryMinutes * 60L * 1000L;
      c.resolutionGapMs = Math.max(1, resolutionGapMinutes) * 60L * 1000L;
      if (suppressionFlags != null && !suppressionFlags.isEmpty()) {
        c.suppressionFlags = new HashSet<>(suppressionFlags);
      }
      if (interruptive != null && !interruptive.isEmpty()) {
        c.interruptiveTiers = new HashSet<>(interruptive);
      }
      if (passive != null && !passive.isEmpty()) {
        c.passiveTiers = new HashSet<>(passive);
      }
      return c;
    }
  }

  public static final class PatientGovState implements Serializable {
    public Integer lastEmittedScore;
    public long lastEmittedEventTimeMs = Long.MIN_VALUE;
    public int crossingsAboveThreshold;
    public long firstCrossingEventTimeMs = Long.MIN_VALUE;
    public long lastCrossingEventTimeMs = Long.MIN_VALUE;
    public Integer firstCrossingScore;
    public Integer baselineScore;
    public long baselineSetAtMs = Long.MIN_VALUE;
    public String encounterId;
    public final Set<String> contextFlags = new HashSet<>();

    public void resetTrajectory() {
      crossingsAboveThreshold = 0;
      firstCrossingEventTimeMs = Long.MIN_VALUE;
      lastCrossingEventTimeMs = Long.MIN_VALUE;
      firstCrossingScore = null;
    }
  }

  /** Minimal alert view mutated in place by governance. */
  public static final class AlertView implements Serializable {
    public Integer score;
    public String tier;
    public String eventTime;
    public String encounterId;
    public String governancePath = "naive";
    public boolean suppressed;
    public String suppressionReason;
    public String pageDeferredReason;
    public Integer positiveComponents;
    public Set<String> contextFlags = new HashSet<>();
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

  /** Explicit resolution / below-threshold signal — resets trajectory. */
  public static void noteBelowThreshold(PatientGovState state) {
    if (state != null) {
      state.resetTrajectory();
    }
  }

  /**
   * Bind state to an encounter. Missing/blank id keeps the current scope. Any identity change —
   * including {@code null → Encounter/X} — clears encounter-scoped fields so flags set before an
   * encounter id cannot leak into the first named encounter.
   */
  static void applyEncounterScope(PatientGovState state, String encounterId) {
    if (encounterId == null || encounterId.isBlank()) {
      return;
    }
    String newId = encounterId.trim();
    if (newId.equals(state.encounterId)) {
      return;
    }
    state.resetTrajectory();
    state.baselineScore = null;
    state.baselineSetAtMs = Long.MIN_VALUE;
    state.lastEmittedEventTimeMs = Long.MIN_VALUE;
    // Context flags are encounter-scoped (e.g. comfort_care must not leak).
    state.contextFlags.clear();
    state.encounterId = newId;
  }

  public static Decision evaluate(AlertView naive, PatientGovState state, Config config) {
    if (naive == null) {
      return new Decision(false, true, "no_alert", "none", naive);
    }
    long eventTimeMs = parseMs(naive.eventTime);

    applyEncounterScope(state, naive.encounterId);

    if (naive.contextFlags != null) {
      state.contextFlags.addAll(naive.contextFlags);
    }

    // Recovery: below-threshold / tier none — do not count as a crossing.
    String tierRaw = naive.tier == null ? "none" : naive.tier.toLowerCase(Locale.ROOT);
    if ("none".equals(tierRaw) || naive.score == null) {
      noteBelowThreshold(state);
      naive.suppressed = true;
      naive.suppressionReason = "below_threshold";
      naive.governancePath = "governed";
      return new Decision(false, true, "below_threshold", "none", naive);
    }

    Set<String> flags = new HashSet<>(state.contextFlags);
    if (naive.contextFlags != null) {
      flags.addAll(naive.contextFlags);
    }
    for (String flag : flags) {
      if (config.suppressionFlags.contains(flag)) {
        naive.suppressed = true;
        naive.suppressionReason = "context:" + flag;
        naive.governancePath = "governed";
        return new Decision(false, true, naive.suppressionReason, "none", naive);
      }
    }

    // Expire baseline after lookback window so re-deterioration can re-establish it.
    if (config.baselineEnabled
        && state.baselineScore != null
        && state.baselineSetAtMs != Long.MIN_VALUE
        && eventTimeMs - state.baselineSetAtMs > config.baselineLookbackMs) {
      state.baselineScore = null;
      state.baselineSetAtMs = Long.MIN_VALUE;
    }

    // Recovery gap: prior crossing streak expired
    if (state.lastCrossingEventTimeMs != Long.MIN_VALUE
        && eventTimeMs - state.lastCrossingEventTimeMs > config.resolutionGapMs) {
      state.resetTrajectory();
    }

    // Count unique event times only (dedup Kafka redeliveries / duplicate alerts)
    if (state.lastCrossingEventTimeMs != eventTimeMs) {
      if (state.firstCrossingEventTimeMs == Long.MIN_VALUE) {
        state.firstCrossingEventTimeMs = eventTimeMs;
        state.firstCrossingScore = naive.score;
        state.crossingsAboveThreshold = 1;
      } else {
        state.crossingsAboveThreshold += 1;
      }
      state.lastCrossingEventTimeMs = eventTimeMs;
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
      state.baselineSetAtMs = eventTimeMs;
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

    String tier = tierRaw;
    String pageDefer = pageDeferReason(state, config, naive.score, naive, persisted);
    String routing;
    String reason = "pass";
    if (config.interruptiveTiers.contains(tier)) {
      if (pageDefer == null) {
        routing = "interruptive";
      } else {
        routing = "passive";
        reason = "pass_watch:" + pageDefer;
        naive.pageDeferredReason = pageDefer;
      }
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
    return new Decision(true, false, reason, routing, naive);
  }

  /** {@code null} when page gates pass (or page gate disabled). */
  static String pageDeferReason(
      PatientGovState state, Config config, int score, AlertView alert, long persistedMs) {
    if (!config.pageGateEnabled) {
      return null;
    }
    if (state.crossingsAboveThreshold < config.pageMinCrossings) {
      return "page_crossings";
    }
    if (persistedMs < config.pageTrajectoryPersistenceMs) {
      return "page_persistence";
    }
    if (config.pageMinScoreDelta > 0
        && state.firstCrossingScore != null
        && score - state.firstCrossingScore < config.pageMinScoreDelta) {
      return "page_not_rising";
    }
    if (config.pageMinPositiveComponents > 0
        && (alert.positiveComponents == null
            || alert.positiveComponents < config.pageMinPositiveComponents)) {
      return "page_components";
    }
    return null;
  }

  private static long parseMs(String iso) {
    if (iso == null || iso.isBlank()) {
      return Instant.EPOCH.toEpochMilli();
    }
    return Instant.parse(iso.replace(" ", "T")).toEpochMilli();
  }
}
