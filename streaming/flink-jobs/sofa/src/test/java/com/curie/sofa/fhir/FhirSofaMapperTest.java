package com.curie.sofa.fhir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.curie.sofa.fhir.FhirSofaMapper.ExtractResult;
import com.curie.sofa.scoring.SofaScorer.Component;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

class FhirSofaMapperTest {

  private final ObjectMapper mapper = new ObjectMapper();

  @Test
  void mapsPlateletsObservationWithValidUnit() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "plt-1");
    obs.put("status", "final");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", FhirSofaMapper.LOINC_PLATELETS);
    obs.putObject("valueQuantity").put("value", 40).put("unit", "10*9/L");

    ExtractResult result = FhirSofaMapper.extractValidated(obs);
    assertEquals(1, result.inputs.size());
    assertEquals(Component.COAGULATION, result.inputs.get(0).name);
    assertEquals(40.0, result.inputs.get(0).platelets10e9L);
    assertEquals("Observation/plt-1", result.inputs.get(0).evidenceIds.get(0));
    assertTrue(result.invalid.isEmpty());
  }

  @Test
  void invalidUnitGoesToDlqReason() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "plt-bad");
    obs.put("status", "final");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", FhirSofaMapper.LOINC_PLATELETS);
    obs.putObject("valueQuantity").put("value", 40).put("unit", "g/dL");

    ExtractResult result = FhirSofaMapper.extractValidated(obs);
    assertTrue(result.inputs.isEmpty());
    assertEquals(1, result.invalid.size());
    assertEquals("invalid_unit", result.invalid.get(0).reason);
  }

  @Test
  void cancelledStatusRejected() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "plt-x");
    obs.put("status", "cancelled");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("code", FhirSofaMapper.LOINC_PLATELETS);
    obs.putObject("valueQuantity").put("value", 40).put("unit", "10*9/L");

    ExtractResult result = FhirSofaMapper.extractValidated(obs);
    assertTrue(result.inputs.isEmpty());
    assertTrue(result.invalid.get(0).reason.startsWith("invalid_status"));
  }

  @Test
  void spo2StoresRawPercentWithoutAmbientProxy() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "spo2-1");
    obs.put("status", "final");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", FhirSofaMapper.LOINC_SPO2);
    obs.putObject("valueQuantity").put("value", 98).put("unit", "%");

    ExtractResult result = FhirSofaMapper.extractValidated(obs);
    assertEquals(1, result.inputs.size());
    assertEquals(98.0, result.inputs.get(0).spo2Percent);
    assertNull(result.inputs.get(0).spo2Fio2);
    assertTrue(result.invalid.isEmpty());
  }

  @Test
  void fio2StoresFraction() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "fio2-1");
    obs.put("status", "final");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", FhirSofaMapper.LOINC_FIO2);
    obs.putObject("valueQuantity").put("value", 40).put("unit", "%");

    ExtractResult result = FhirSofaMapper.extractValidated(obs);
    assertEquals(1, result.inputs.size());
    assertEquals(0.4, result.inputs.get(0).fio2Fraction);
  }
}
