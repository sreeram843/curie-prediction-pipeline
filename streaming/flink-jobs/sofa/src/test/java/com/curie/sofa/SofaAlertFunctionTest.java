package com.curie.sofa;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.curie.sofa.model.CanonicalEvent;
import com.curie.sofa.operators.SofaAlertFunction;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class SofaAlertFunctionTest {
  @Test
  void availabilityClockUsesExplicitAvailabilityThenIngestThenEvent() {
    CanonicalEvent explicit = new CanonicalEvent();
    explicit.event_time = "2024-01-01T09:00:00Z";
    explicit.ingest_time = "2024-01-01T09:45:00Z";
    explicit.availability_time = "2024-01-01T10:00:00Z";
    assertEquals(
        Instant.parse("2024-01-01T10:00:00Z").toEpochMilli(),
        SofaAlertFunction.effectiveAvailabilityTimeMs(explicit));

    CanonicalEvent ingest = new CanonicalEvent();
    ingest.event_time = explicit.event_time;
    ingest.ingest_time = explicit.ingest_time;
    assertEquals(
        Instant.parse("2024-01-01T09:45:00Z").toEpochMilli(),
        SofaAlertFunction.effectiveAvailabilityTimeMs(ingest));

    CanonicalEvent event = new CanonicalEvent();
    event.event_time = explicit.event_time;
    assertEquals(
        Instant.parse("2024-01-01T09:00:00Z").toEpochMilli(),
        SofaAlertFunction.effectiveAvailabilityTimeMs(event));
  }
}
