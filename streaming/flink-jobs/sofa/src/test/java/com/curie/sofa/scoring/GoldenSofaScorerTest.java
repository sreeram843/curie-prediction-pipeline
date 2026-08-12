package com.curie.sofa.scoring;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.curie.sofa.scoring.SofaScorer.Completeness;
import com.curie.sofa.scoring.SofaScorer.ScoreResult;
import com.curie.sofa.scoring.SofaScorer.Tier;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** Loads shared golden JSON (also under eval/fixtures/golden) and asserts Java parity. */
class GoldenSofaScorerTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  void goldenCasesMatchPythonContract() throws Exception {
    RuleBundle bundle;
    try (InputStream bin =
        GoldenSofaScorerTest.class.getResourceAsStream("/golden/sepsis-sofa.v0.2.0.json")) {
      bundle = MAPPER.readValue(bin, RuleBundle.class);
    }
    SofaThresholds thresholds = SofaThresholds.fromBundle(bundle);
    try (InputStream in =
        GoldenSofaScorerTest.class.getResourceAsStream("/golden/sofa_cases.v0.2.json")) {
      JsonNode root = MAPPER.readTree(in);
      String bundleId = root.get("rule_bundle_id").asText();
      String version = root.get("rule_version").asText();
      for (JsonNode c : root.get("cases")) {
        List<ComponentInput> inputs = parseInputs(c.get("inputs"));
        ScoreResult r =
            SofaScorer.compute(
                "Patient/golden-" + c.get("id").asText(),
                null,
                0L,
                inputs,
                bundleId,
                version,
                3,
                thresholds);
        JsonNode expect = c.get("expect");
        if (expect.get("total_score").isNull()) {
          assertNull(r.totalScore, c.get("id").asText());
        } else {
          assertEquals(expect.get("total_score").asInt(), r.totalScore.intValue(), c.get("id").asText());
        }
        assertEquals(
            Completeness.valueOf(expect.get("completeness").asText().toUpperCase()),
            r.completeness,
            c.get("id").asText());
        Tier tier = SofaScorer.tierForScore(r.totalScore, 2);
        assertEquals(expect.get("tier").asText(), tier.wireName(), c.get("id").asText());
      }
    }
  }

  private static List<ComponentInput> parseInputs(JsonNode inputs) {
    List<ComponentInput> out = new ArrayList<>();
    Iterator<Map.Entry<String, JsonNode>> fields = inputs.fields();
    while (fields.hasNext()) {
      Map.Entry<String, JsonNode> e = fields.next();
      Component name = Component.fromWire(e.getKey());
      ComponentInput in = new ComponentInput(name);
      JsonNode v = e.getValue();
      if (v.hasNonNull("pao2_fio2")) {
        in.pao2Fio2 = v.get("pao2_fio2").asDouble();
      }
      if (v.hasNonNull("spo2_fio2")) {
        in.spo2Fio2 = v.get("spo2_fio2").asDouble();
      }
      if (v.hasNonNull("mechanically_ventilated")) {
        in.mechanicallyVentilated = v.get("mechanically_ventilated").asBoolean();
      }
      if (v.hasNonNull("platelets_10e9_l")) {
        in.platelets10e9L = v.get("platelets_10e9_l").asDouble();
      }
      if (v.hasNonNull("bilirubin_mg_dl")) {
        in.bilirubinMgDl = v.get("bilirubin_mg_dl").asDouble();
      }
      if (v.hasNonNull("map_mmhg")) {
        in.mapMmhg = v.get("map_mmhg").asDouble();
      }
      if (v.hasNonNull("on_vasopressors")) {
        in.onVasopressors = v.get("on_vasopressors").asBoolean();
      }
      if (v.hasNonNull("vasopressor_agent")) {
        in.vasopressorAgent = v.get("vasopressor_agent").asText();
      }
      if (v.hasNonNull("vasopressor_dose_ug_kg_min")) {
        in.vasopressorDoseUgKgMin = v.get("vasopressor_dose_ug_kg_min").asDouble();
      }
      if (v.hasNonNull("gcs")) {
        in.gcs = v.get("gcs").asInt();
      }
      if (v.hasNonNull("creatinine_mg_dl")) {
        in.creatinineMgDl = v.get("creatinine_mg_dl").asDouble();
      }
      if (v.hasNonNull("urine_output_ml_day")) {
        in.urineOutputMlDay = v.get("urine_output_ml_day").asDouble();
      }
      out.add(in);
    }
    return out;
  }
}
