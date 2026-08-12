package com.curie.sofa.state;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Deterministic event-time reorder buffer (CURIE-006 / CURIE-026).
 *
 * <p>Within {@code allowedLatenessMs}, arrivals are buffered and flushed in {@code (eventTimeMs,
 * tieBreaker)} order. Beyond lateness: disposition {@code late_beyond_lateness} — do not mutate
 * feature/governance state; late corrections do not retract prior alerts.
 *
 * <p>A single event is not flushed from {@link #offer} alone: watermark starts at {@code eventTime -
 * lateness}. Operators must register an event-time timer at {@link #flushTimerTimestamp(long)} (or
 * call {@link #advanceWatermark(long)} / {@link #close()}) so the final event for a key still
 * scores without a following arrival.
 */
public final class EventTimeBuffer<T> implements Serializable {
  public static final String LATE_DISPOSITION = "late_beyond_lateness";

  /** Shared SOFA/AKI event-time policy version (CURIE-026 / CURIE-027). */
  public static final String POLICY_VERSION = "event-time-v1-lateness-5m";

  public static final class BufferedEvent<T> implements Serializable {
    public final long eventTimeMs;
    public final String tieBreaker;
    public final T payload;

    public BufferedEvent(long eventTimeMs, String tieBreaker, T payload) {
      this.eventTimeMs = eventTimeMs;
      this.tieBreaker = tieBreaker != null ? tieBreaker : "";
      this.payload = payload;
    }
  }

  public static final class FlushResult<T> implements Serializable {
    public final List<BufferedEvent<T>> ready = new ArrayList<>();
    public final List<BufferedEvent<T>> late = new ArrayList<>();
    public final String dispositionLate = LATE_DISPOSITION;
  }

  private final long allowedLatenessMs;
  private final List<BufferedEvent<T>> pending = new ArrayList<>();
  private Long maxEventTimeMs;
  private long watermarkMs;

  public EventTimeBuffer(long allowedLatenessMs) {
    if (allowedLatenessMs < 0) {
      throw new IllegalArgumentException("allowedLatenessMs must be >= 0");
    }
    this.allowedLatenessMs = allowedLatenessMs;
  }

  public long allowedLatenessMs() {
    return allowedLatenessMs;
  }

  public long watermarkMs() {
    return watermarkMs;
  }

  public Long maxEventTimeMs() {
    return maxEventTimeMs;
  }

  public int pendingCount() {
    return pending.size();
  }

  public String policyVersion() {
    return POLICY_VERSION;
  }

  /**
   * Event-time timer timestamp that advances the local watermark far enough to flush {@code
   * eventTimeMs} (and any earlier pending events).
   */
  public long flushTimerTimestamp(long eventTimeMs) {
    return eventTimeMs + allowedLatenessMs;
  }

  /**
   * Advance the local watermark (e.g. from an event-time timer) and flush eligible pending
   * events. Watermark only moves forward.
   */
  public FlushResult<T> advanceWatermark(long newWatermarkMs) {
    if (newWatermarkMs > watermarkMs) {
      watermarkMs = newWatermarkMs;
    }
    return flushReady();
  }

  public FlushResult<T> offer(long eventTimeMs, T payload, String tieBreaker) {
    if (maxEventTimeMs == null || eventTimeMs > maxEventTimeMs) {
      maxEventTimeMs = eventTimeMs;
      watermarkMs = Math.max(0L, eventTimeMs - allowedLatenessMs);
    }
    FlushResult<T> out = new FlushResult<>();
    if (eventTimeMs < watermarkMs) {
      out.late.add(new BufferedEvent<>(eventTimeMs, tieBreaker, payload));
      return out;
    }
    pending.add(new BufferedEvent<>(eventTimeMs, tieBreaker, payload));
    return flushReady();
  }

  public FlushResult<T> close() {
    watermarkMs = maxEventTimeMs != null ? maxEventTimeMs + 1 : 0L;
    return flushReady();
  }

  public List<BufferedEvent<T>> snapshotPending() {
    return new ArrayList<>(pending);
  }

  public void restorePending(List<BufferedEvent<T>> events) {
    pending.clear();
    pending.addAll(events);
    maxEventTimeMs = null;
    for (BufferedEvent<T> e : pending) {
      if (maxEventTimeMs == null || e.eventTimeMs > maxEventTimeMs) {
        maxEventTimeMs = e.eventTimeMs;
      }
    }
    watermarkMs =
        maxEventTimeMs == null ? 0L : Math.max(0L, maxEventTimeMs - allowedLatenessMs);
  }

  private FlushResult<T> flushReady() {
    FlushResult<T> out = new FlushResult<>();
    List<BufferedEvent<T>> stay = new ArrayList<>();
    for (BufferedEvent<T> ev : pending) {
      if (ev.eventTimeMs <= watermarkMs) {
        out.ready.add(ev);
      } else {
        stay.add(ev);
      }
    }
    pending.clear();
    pending.addAll(stay);
    out.ready.sort(
        Comparator.comparingLong((BufferedEvent<T> e) -> e.eventTimeMs)
            .thenComparing(e -> e.tieBreaker));
    return out;
  }
}
