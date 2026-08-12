package com.curie.sofa.model;

import java.io.Serializable;

/** Dead-letter queue for invalid clinical events (fail closed, visibly). */
public class DlqEvent implements Serializable {
  public String schema_version = "1.0.0";
  public String patient_id;
  public String encounter_id;
  public String event_time;
  public String ingest_time;
  public String idempotency_key;
  public String reason;
  public String resource_type;
  public String resource_id;
  public String code;
  public String unit;
  public String status;
  public String source = "sofa-fhir-mapper";
}
