package com.curie.sofa.state;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class EventTimeBufferTest {
  @Test
  void permutationsWithinLatenessSameOrderOnClose() {
    List<String[]> events =
        Arrays.asList(
            new String[] {"1000", "a", "A"},
            new String[] {"2000", "b", "B"},
            new String[] {"3000", "c", "C"});
    List<List<String>> results = new ArrayList<>();
    permute(events, 0, results);
    List<String> first = results.get(0);
    for (List<String> r : results) {
      assertEquals(first, r);
    }
    assertEquals(Arrays.asList("A", "B", "C"), first);
  }

  @Test
  void beyondLatenessDropped() {
    EventTimeBuffer<String> buf = new EventTimeBuffer<>(1_000);
    buf.offer(10_000, "new", "n");
    EventTimeBuffer.FlushResult<String> late = buf.offer(8_000, "old", "o");
    assertEquals(1, late.late.size());
    assertEquals("o", late.late.get(0).tieBreaker);
    assertEquals(EventTimeBuffer.LATE_DISPOSITION, late.dispositionLate);
  }

  @Test
  void equalTimestampUsesTieBreaker() {
    EventTimeBuffer<String> buf = new EventTimeBuffer<>(60_000);
    buf.offer(5_000, "second", "b");
    buf.offer(5_000, "first", "a");
    List<String> out = new ArrayList<>();
    for (EventTimeBuffer.BufferedEvent<String> e : buf.close().ready) {
      out.add(e.payload);
    }
    assertEquals(Arrays.asList("first", "second"), out);
  }

  @Test
  void restartRestorePending() {
    EventTimeBuffer<String> buf = new EventTimeBuffer<>(5_000);
    buf.offer(10_000, "a", "a");
    buf.offer(11_000, "b", "b");
    List<EventTimeBuffer.BufferedEvent<String>> snap = buf.snapshotPending();
    EventTimeBuffer<String> restored = new EventTimeBuffer<>(5_000);
    restored.restorePending(snap);
    List<String> out = new ArrayList<>();
    for (EventTimeBuffer.BufferedEvent<String> e : restored.close().ready) {
      out.add(e.payload);
    }
    assertEquals(Arrays.asList("a", "b"), out);
  }

  @Test
  void singleEventFlushesViaWatermarkAdvanceWithoutFollower() {
    EventTimeBuffer<String> buf = new EventTimeBuffer<>(5 * 60 * 1000L);
    EventTimeBuffer.FlushResult<String> afterOffer = buf.offer(10_000, "only", "k1");
    assertTrue(afterOffer.ready.isEmpty());
    assertEquals(1, buf.pendingCount());
    long timer = buf.flushTimerTimestamp(10_000);
    assertEquals(10_000 + 5 * 60 * 1000L, timer);
    EventTimeBuffer.FlushResult<String> flushed = buf.advanceWatermark(timer);
    assertEquals(1, flushed.ready.size());
    assertEquals("only", flushed.ready.get(0).payload);
    assertEquals(0, buf.pendingCount());
    assertEquals(EventTimeBuffer.POLICY_VERSION, buf.policyVersion());
  }

  @Test
  void advanceWatermarkIsMonotonic() {
    EventTimeBuffer<String> buf = new EventTimeBuffer<>(1_000);
    buf.offer(5_000, "a", "a");
    buf.advanceWatermark(5_000);
    assertEquals(5_000, buf.watermarkMs());
    buf.advanceWatermark(4_000);
    assertEquals(5_000, buf.watermarkMs());
  }

  private static void permute(
      List<String[]> events, int start, List<List<String>> results) {
    if (start == events.size()) {
      EventTimeBuffer<String> buf = new EventTimeBuffer<>(60_000);
      for (String[] e : events) {
        buf.offer(Long.parseLong(e[0]), e[2], e[1]);
      }
      List<String> out = new ArrayList<>();
      for (EventTimeBuffer.BufferedEvent<String> ev : buf.close().ready) {
        out.add(ev.payload);
      }
      results.add(out);
      return;
    }
    for (int i = start; i < events.size(); i++) {
      Collections.swap(events, start, i);
      permute(events, start + 1, results);
      Collections.swap(events, start, i);
    }
  }
}
