package com.curie.sofa.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.Serializable;

/** Canonical Kafka envelope (subset needed by the SOFA job). */
@JsonIgnoreProperties(ignoreUnknown = true)
public class CanonicalEvent implements Serializable {
  public String schema_version;
  public String patient_id;
  public String encounter_id;
  public String resource_type;
  public JsonNode resource;
  public String event_time;
  public String ingest_time;
  public String source;
  public String idempotency_key;
}
