package com.curie.sofa.model;

import com.curie.sofa.scoring.SofaScorer;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/** Internal alert event written to the {@code alerts} Kafka topic. */
public class AlertEvent implements Serializable {
  public String schema_version = "1.0.0";
  public String alert_id;
  public String patient_id;
  public String encounter_id;
  public String indicator = "sepsis";
  public String event_time;
  public String ingest_time;
  public Integer score;
  public String completeness;
  public String tier;
  public List<ComponentBreakdown> component_breakdown = new ArrayList<>();
  public List<String> missing_components = new ArrayList<>();
  public List<String> evidence_ids = new ArrayList<>();
  public String rule_bundle_id;
  public String rule_version;
  public String governance_path = "naive";
  public boolean suppressed = false;
  public String suppression_reason;
  public java.util.List<String> context_flags = new java.util.ArrayList<>();

  public static class ComponentBreakdown implements Serializable {
    public String name;
    public Integer points;
    public boolean missing;
    public List<String> evidence_ids = new ArrayList<>();
  }

  public static AlertEvent fromScore(
      SofaScorer.ScoreResult score, SofaScorer.Tier tier, String alertId, String ingestTimeIso) {
    AlertEvent a = new AlertEvent();
    a.alert_id = alertId;
    a.patient_id = score.patientId;
    a.encounter_id = score.encounterId;
    a.event_time = java.time.Instant.ofEpochMilli(score.eventTimeEpochMs).toString();
    a.ingest_time = ingestTimeIso;
    a.score = score.totalScore;
    a.completeness = score.completeness.wireName();
    a.tier = tier.wireName();
    a.rule_bundle_id = score.ruleBundleId;
    a.rule_version = score.ruleVersion;
    a.evidence_ids = new ArrayList<>(score.evidenceIds);
    for (SofaScorer.ComponentScore c : score.components) {
      ComponentBreakdown b = new ComponentBreakdown();
      b.name = c.name.wireName();
      b.points = c.points;
      b.missing = c.missing;
      b.evidence_ids = new ArrayList<>(c.evidenceIds);
      a.component_breakdown.add(b);
      if (c.missing) {
        a.missing_components.add(c.name.wireName());
      }
    }
    return a;
  }

  public static AlertEvent fromAki(
      com.curie.sofa.aki.AkiScorer.Result score,
      String tier,
      String alertId,
      String ingestTimeIso) {
    AlertEvent a = new AlertEvent();
    a.alert_id = alertId;
    a.patient_id = score.patientId;
    a.encounter_id = score.encounterId;
    a.indicator = "aki";
    a.event_time = java.time.Instant.ofEpochMilli(score.eventTimeEpochMs).toString();
    a.ingest_time = ingestTimeIso;
    a.score = score.totalScore;
    a.completeness = score.completeness;
    a.tier = tier;
    a.rule_bundle_id = score.ruleBundleId;
    a.rule_version = score.ruleVersion;
    a.evidence_ids = new ArrayList<>(score.evidenceIds);
    a.missing_components = new ArrayList<>(score.missingComponents);
    ComponentBreakdown stage = new ComponentBreakdown();
    stage.name = "aki_stage";
    stage.points = score.stage;
    stage.missing = score.stage == null;
    a.component_breakdown.add(stage);
    return a;
  }
}
