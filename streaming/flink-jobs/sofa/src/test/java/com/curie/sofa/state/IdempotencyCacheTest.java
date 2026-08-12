package com.curie.sofa.state;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class IdempotencyCacheTest {

  @Test
  void duplicateWithinTtlRejected() {
    IdempotencyCache cache = new IdempotencyCache(60_000L, 100);
    assertFalse(cache.seen("k1", 1_000L));
    assertTrue(cache.seen("k1", 2_000L));
  }

  @Test
  void expiredKeyCanBeReaccepted() {
    IdempotencyCache cache = new IdempotencyCache(1_000L, 100);
    assertFalse(cache.seen("k1", 0L));
    assertFalse(cache.seen("k1", 2_000L));
  }

  @Test
  void capacityEvictsEldestWithoutClearingAll() {
    IdempotencyCache cache = new IdempotencyCache(60_000L, 3);
    assertFalse(cache.seen("a", 1L));
    assertFalse(cache.seen("b", 2L));
    assertFalse(cache.seen("c", 3L));
    assertFalse(cache.seen("d", 4L)); // evicts a
    assertTrue(cache.seen("b", 5L));
    assertTrue(cache.seen("c", 5L));
    assertTrue(cache.seen("d", 5L));
    assertFalse(cache.seen("a", 6L)); // a was evicted, not bulk-cleared mid-flight
  }
}
