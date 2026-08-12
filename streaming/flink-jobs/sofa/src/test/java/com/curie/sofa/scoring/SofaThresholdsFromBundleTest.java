package com.curie.sofa.scoring;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.model.RuleBundle;
import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

class SofaThresholdsFromBundleTest {

  private final ObjectMapper mapper = new ObjectMapper();

  @Test
  void coagulationBandsFromBundleChangePlateletScore() {
    RuleBundle rules = RuleBundle.defaults();
    ObjectNode ct = mapper.createObjectNode();
    ArrayNode coagBands = ct.putObject("coagulation").putArray("bands");
    coagBands.addObject().put("points", 4).put("max_exclusive", 30);
    coagBands.addObject().put("points", 3).put("max_exclusive", 50);
    coagBands.addObject().put("points", 2).put("max_exclusive", 100);
    coagBands.addObject().put("points", 1).put("max_exclusive", 150);
    coagBands.addObject().put("points", 0).put("min_inclusive", 150);
    rules.score.component_thresholds = ct;

    SofaThresholds th = SofaThresholds.fromBundle(rules);
    ComponentInput in = new ComponentInput(Component.COAGULATION);
    in.platelets10e9L = 25.0;
    assertEquals(4, SofaScorer.scoreCoagulation(in, th));
    assertEquals(3, SofaScorer.scoreCoagulation(in, SofaThresholds.defaults()));
  }
}
