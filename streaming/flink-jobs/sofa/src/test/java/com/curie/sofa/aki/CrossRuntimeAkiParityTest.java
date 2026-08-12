package com.curie.sofa.aki;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** CURIE-007: AKI cases from shared cross_runtime_parity.v1.json */
class CrossRuntimeAkiParityTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  void akiCasesMatchPythonContract() throws Exception {
    int n = 0;
    try (InputStream in =
        CrossRuntimeAkiParityTest.class.getResourceAsStream(
            "/golden/cross_runtime_parity.v1.json")) {
      JsonNode root = MAPPER.readTree(in);
      for (JsonNode c : root.get("aki_cases")) {
        n++;
        JsonNode inputs = c.get("inputs");
        AkiScorer.Input inAki = new AkiScorer.Input();
        if (inputs.hasNonNull("creatinine_mg_dl")) {
          inAki.creatinineMgDl = inputs.get("creatinine_mg_dl").asDouble();
        }
        if (inputs.hasNonNull("baseline_creatinine_mg_dl")) {
          inAki.baselineCreatinineMgDl = inputs.get("baseline_creatinine_mg_dl").asDouble();
        }
        if (inputs.hasNonNull("urine_ml_kg_h")) {
          inAki.urineMlKgH = inputs.get("urine_ml_kg_h").asDouble();
        }
        if (inputs.hasNonNull("urine_duration_hours")) {
          inAki.urineDurationHours = inputs.get("urine_duration_hours").asDouble();
        }
        AkiScorer.Result r =
            AkiScorer.compute("Patient/parity-" + c.get("id").asText(), null, 0L, inAki, "0.3.0");
        JsonNode expect = c.get("expect");
        assertEquals(expect.get("stage").asInt(), r.stage, c.get("id").asText());
        assertEquals(expect.get("total_score").asInt(), r.totalScore, c.get("id").asText());
        assertEquals(expect.get("completeness").asText(), r.completeness, c.get("id").asText());
        if (expect.has("missing_components")) {
          Set<String> missing = new HashSet<>(r.missingComponents);
          Set<String> want = new HashSet<>();
          for (JsonNode m : expect.get("missing_components")) {
            want.add(m.asText());
          }
          assertEquals(want, missing, c.get("id").asText());
        }
        if (expect.has("creatinine_stage")) {
          assertEquals(
              expect.get("creatinine_stage").asInt(), r.creatinineStage, c.get("id").asText());
        }
        if (expect.has("urine_stage")) {
          assertEquals(expect.get("urine_stage").asInt(), r.urineStage, c.get("id").asText());
        }
      }
    }
    assertTrue(n >= 1, "expected AKI fixtures");
  }
}
