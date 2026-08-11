package com.curie.sofa.fhir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class FhirSofaMapperTest {

  private final ObjectMapper mapper = new ObjectMapper();

  @Test
  void mapsPlateletsObservation() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "plt-1");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", FhirSofaMapper.LOINC_PLATELETS);
    obs.putObject("valueQuantity").put("value", 40);

    Optional<ComponentInput> mapped = FhirSofaMapper.fromObservation(obs);
    assertTrue(mapped.isPresent());
    assertEquals(Component.COAGULATION, mapped.get().name);
    assertEquals(40.0, mapped.get().platelets10e9L);
    assertEquals("Observation/plt-1", mapped.get().evidenceIds.get(0));
  }
}
