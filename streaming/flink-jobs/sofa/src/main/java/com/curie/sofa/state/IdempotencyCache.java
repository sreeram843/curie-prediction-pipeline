package com.curie.sofa.state;

import java.io.Serializable;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Bounded idempotency cache with TTL. Evicts expired entries first; if still over capacity, drops
 * eldest (insertion order) — never clears the whole map.
 */
public final class IdempotencyCache implements Serializable {
  private static final long serialVersionUID = 1L;

  public static final long DEFAULT_TTL_MS = 24L * 60L * 60L * 1000L;
  public static final int DEFAULT_MAX_KEYS = 10_000;

  private final LinkedHashMap<String, Long> entries = new LinkedHashMap<>();
  private final long ttlMs;
  private final int maxKeys;

  public IdempotencyCache() {
    this(DEFAULT_TTL_MS, DEFAULT_MAX_KEYS);
  }

  public IdempotencyCache(long ttlMs, int maxKeys) {
    this.ttlMs = ttlMs;
    this.maxKeys = maxKeys;
  }

  /** @return true if this key was already seen within TTL (duplicate). */
  public boolean seen(String key, long nowMs) {
    if (key == null || key.isBlank()) {
      return false;
    }
    pruneExpired(nowMs);
    Long prior = entries.get(key);
    if (prior != null && nowMs - prior < ttlMs) {
      return true;
    }
    entries.put(key, nowMs);
    while (entries.size() > maxKeys) {
      Iterator<Map.Entry<String, Long>> it = entries.entrySet().iterator();
      if (!it.hasNext()) {
        break;
      }
      it.next();
      it.remove();
    }
    return false;
  }

  public int size() {
    return entries.size();
  }

  void pruneExpired(long nowMs) {
    Iterator<Map.Entry<String, Long>> it = entries.entrySet().iterator();
    while (it.hasNext()) {
      Map.Entry<String, Long> e = it.next();
      if (nowMs - e.getValue() >= ttlMs) {
        it.remove();
      }
    }
  }
}
