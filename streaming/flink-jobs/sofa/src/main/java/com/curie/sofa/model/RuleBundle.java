package com.curie.sofa.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/** Versioned rule bundle broadcast into Flink (matches streaming/rule-registry/bundles). */
@JsonIgnoreProperties(ignoreUnknown = true)
public class RuleBundle implements Serializable {
  public String bundle_id = "sepsis-sofa";
  public String version = "0.1.0";
  public String indicator = "sepsis";
  public AlertConfig alert = new AlertConfig();
  public ScoreConfig score = new ScoreConfig();
  public GovernanceConfig governance = new GovernanceConfig();

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class AlertConfig implements Serializable {
    public int naive_threshold = 2;
    public List<SeverityBand> severity_bands = new ArrayList<>();
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class SeverityBand implements Serializable {
    public int min;
    public int max;
    public String tier;
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class ScoreConfig implements Serializable {
    public String type = "sofa";
    public String missing_policy = "partial_with_missing_components";
    public int min_components_required = 3;
    /** Raw JSON object from the rule bundle — interpreted by {@link com.curie.sofa.scoring.SofaThresholds}. */
    public com.fasterxml.jackson.databind.JsonNode component_thresholds;
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class GovernanceConfig implements Serializable {
    public Trajectory trajectory = new Trajectory();
    public Baseline baseline = new Baseline();
    public Suppression suppression = new Suppression();
    public Dedup dedup = new Dedup();
    public Tiering tiering = new Tiering();
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class Trajectory implements Serializable {
    public int min_persistence_minutes = 30;
    public int min_crossings = 2;
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class Baseline implements Serializable {
    public boolean enabled = true;
    public int lookback_hours = 24;
    public int delta_threshold = 2;
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class Suppression implements Serializable {
    public List<String> flags = new ArrayList<>();
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class Dedup implements Serializable {
    public int refractory_minutes = 120;
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public static class Tiering implements Serializable {
    public List<String> interruptive_tiers = new ArrayList<>();
    public List<String> passive_tiers = new ArrayList<>();
  }

  public static RuleBundle defaults() {
    RuleBundle b = new RuleBundle();
    b.bundle_id = "sepsis-sofa";
    b.version = "0.2.0";
    b.alert.naive_threshold = 2;
    SeverityBand watch = new SeverityBand();
    watch.min = 2;
    watch.max = 3;
    watch.tier = "watch";
    SeverityBand urgent = new SeverityBand();
    urgent.min = 4;
    urgent.max = 6;
    urgent.tier = "urgent";
    SeverityBand critical = new SeverityBand();
    critical.min = 7;
    critical.max = 24;
    critical.tier = "critical";
    b.alert.severity_bands = java.util.List.of(watch, urgent, critical);
    b.governance.trajectory.min_persistence_minutes = 30;
    b.governance.trajectory.min_crossings = 2;
    b.governance.baseline.enabled = true;
    b.governance.baseline.delta_threshold = 2;
    b.governance.dedup.refractory_minutes = 120;
    b.governance.suppression.flags =
        new java.util.ArrayList<>(java.util.List.of("comfort_care", "already_on_sepsis_protocol"));
    b.governance.tiering.interruptive_tiers =
        new java.util.ArrayList<>(java.util.List.of("urgent", "critical"));
    b.governance.tiering.passive_tiers =
        new java.util.ArrayList<>(java.util.List.of("watch"));
    return b;
  }
}