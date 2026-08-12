package com.curie.sofa.scoring;

import com.curie.sofa.model.RuleBundle;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

/** Numeric SOFA cutoffs loaded from rule-bundle {@code score.component_thresholds}. */
public final class SofaThresholds implements Serializable {
  public double respP4Lt = 100;
  public double respP3Lt = 200;
  public double respP2Lt = 300;
  public double respP1Lt = 400;
  public double mapLt = 70;
  public int mapPoints = 1;
  public double dopamineP2Max = 5;
  public double dopamineP3Max = 15;
  public double epiNorepiP3Max = 0.1;
  public int unknownPressorPoints = 3;

  // Coag max_exclusive ladder (points 4..1), then min_inclusive for 0
  public double[] coagMaxExclusive = {20, 50, 100, 150};
  public int[] coagPoints = {4, 3, 2, 1};
  public double coagMinInclusiveZero = 150;

  public double[] liverMinInclusive = {12, 6, 2, 1.2};
  public int[] liverPoints = {4, 3, 2, 1};

  public int cnsLt4 = 6;
  public int cnsLe3 = 9;
  public int cnsLe2 = 12;
  public int cnsLe1 = 14;

  public double[] renalCrMin = {5.0, 3.5, 2.0, 1.2};
  public int[] renalCrPoints = {4, 3, 2, 1};
  public double[] renalUoMax = {200, 500};
  public int[] renalUoPoints = {4, 3};

  public static SofaThresholds defaults() {
    return new SofaThresholds();
  }

  public static SofaThresholds fromBundle(RuleBundle rules) {
    SofaThresholds t = defaults();
    if (rules == null || rules.score == null || rules.score.component_thresholds == null) {
      return t;
    }
    JsonNode ct = rules.score.component_thresholds;
    JsonNode respParams = ct.path("respiration").path("params");
    if (!respParams.isMissingNode()) {
      t.respP4Lt = respParams.path("p4_ratio_lt").asDouble(t.respP4Lt);
      t.respP3Lt = respParams.path("p3_ratio_lt").asDouble(t.respP3Lt);
      t.respP2Lt = respParams.path("p2_ratio_lt").asDouble(t.respP2Lt);
      t.respP1Lt = respParams.path("p1_ratio_lt").asDouble(t.respP1Lt);
    }
    JsonNode cv = ct.path("cardiovascular");
    if (!cv.isMissingNode()) {
      if (cv.has("map_mmhg_lt")) {
        t.mapLt = cv.get("map_mmhg_lt").asDouble();
      }
      if (cv.has("map_mmhg_lt_70_points")) {
        t.mapPoints = cv.get("map_mmhg_lt_70_points").asInt();
      }
      JsonNode cvParams = cv.path("params");
      t.dopamineP2Max = cvParams.path("dopamine_p2_max_inclusive").asDouble(t.dopamineP2Max);
      t.dopamineP3Max = cvParams.path("dopamine_p3_max_inclusive").asDouble(t.dopamineP3Max);
      t.epiNorepiP3Max = cvParams.path("epi_norepi_p3_max_inclusive").asDouble(t.epiNorepiP3Max);
      t.unknownPressorPoints = cvParams.path("unknown_dose_points").asInt(t.unknownPressorPoints);
    }

    JsonNode coagBands = ct.path("coagulation").path("bands");
    if (coagBands.isArray() && coagBands.size() > 0) {
      List<Double> maxEx = new ArrayList<>();
      List<Integer> pts = new ArrayList<>();
      Double zeroMin = null;
      for (JsonNode b : coagBands) {
        int points = b.path("points").asInt();
        if (b.has("max_exclusive")) {
          maxEx.add(b.get("max_exclusive").asDouble());
          pts.add(points);
        } else if (b.has("min_inclusive") && points == 0) {
          zeroMin = b.get("min_inclusive").asDouble();
        }
      }
      if (!maxEx.isEmpty()) {
        t.coagMaxExclusive = toDoubleArray(maxEx);
        t.coagPoints = toIntArray(pts);
      }
      if (zeroMin != null) {
        t.coagMinInclusiveZero = zeroMin;
      }
    }

    JsonNode liverBands = ct.path("liver").path("bands");
    if (liverBands.isArray() && liverBands.size() > 0) {
      List<Double> mins = new ArrayList<>();
      List<Integer> pts = new ArrayList<>();
      for (JsonNode b : liverBands) {
        if (b.has("min_inclusive") && b.path("points").asInt() > 0) {
          mins.add(b.get("min_inclusive").asDouble());
          pts.add(b.path("points").asInt());
        }
      }
      if (!mins.isEmpty()) {
        t.liverMinInclusive = toDoubleArray(mins);
        t.liverPoints = toIntArray(pts);
      }
    }

    JsonNode cnsBands = ct.path("cns").path("bands");
    if (cnsBands.isArray()) {
      for (JsonNode b : cnsBands) {
        int points = b.path("points").asInt();
        if (points == 4 && b.has("gcs_lt")) {
          t.cnsLt4 = b.get("gcs_lt").asInt();
        } else if (points == 3 && b.has("gcs_le")) {
          t.cnsLe3 = b.get("gcs_le").asInt();
        } else if (points == 2 && b.has("gcs_le")) {
          t.cnsLe2 = b.get("gcs_le").asInt();
        } else if (points == 1 && b.has("gcs_le")) {
          t.cnsLe1 = b.get("gcs_le").asInt();
        }
      }
    }

    JsonNode renalCr = ct.path("renal").path("creatinine_mg_dl");
    if (renalCr.isArray() && renalCr.size() > 0) {
      List<Double> mins = new ArrayList<>();
      List<Integer> pts = new ArrayList<>();
      for (JsonNode b : renalCr) {
        if (b.has("min_inclusive") && b.path("points").asInt() > 0) {
          mins.add(b.get("min_inclusive").asDouble());
          pts.add(b.path("points").asInt());
        }
      }
      if (!mins.isEmpty()) {
        t.renalCrMin = toDoubleArray(mins);
        t.renalCrPoints = toIntArray(pts);
      }
    }

    JsonNode renalUo = ct.path("renal").path("urine_output_ml_day");
    if (renalUo.isArray() && renalUo.size() > 0) {
      List<Double> maxes = new ArrayList<>();
      List<Integer> pts = new ArrayList<>();
      for (JsonNode b : renalUo) {
        if (b.has("max_exclusive") && b.path("points").asInt() > 0) {
          maxes.add(b.get("max_exclusive").asDouble());
          pts.add(b.path("points").asInt());
        }
      }
      if (!maxes.isEmpty()) {
        t.renalUoMax = toDoubleArray(maxes);
        t.renalUoPoints = toIntArray(pts);
      }
    }

    return t;
  }

  private static double[] toDoubleArray(List<Double> list) {
    double[] a = new double[list.size()];
    for (int i = 0; i < list.size(); i++) {
      a[i] = list.get(i);
    }
    return a;
  }

  private static int[] toIntArray(List<Integer> list) {
    int[] a = new int[list.size()];
    for (int i = 0; i < list.size(); i++) {
      a[i] = list.get(i);
    }
    return a;
  }
}
