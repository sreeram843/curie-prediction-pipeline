package com.curie.sofa.model;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Canonical alert-id algorithm shared by SOFA and AKI Flink paths. */
public final class AlertIds {
  private AlertIds() {}

  public static String of(
      String patientId,
      String encounterId,
      String indicator,
      Integer score,
      long eventTimeMs,
      String version) {
    String raw =
        String.valueOf(patientId)
            + "|"
            + (encounterId == null ? "" : encounterId)
            + "|"
            + (indicator == null ? "sofa-deterioration" : indicator)
            + "|"
            + score
            + "|"
            + eventTimeMs
            + "|"
            + (version == null ? "" : version);
    return "alert-" + UUID.nameUUIDFromBytes(raw.getBytes(StandardCharsets.UTF_8));
  }
}
