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

  @Test
  void mapsExplicitInvasiveVentilationObservation() {
    ObjectNode obs = mapper.createObjectNode();
    obs.put("resourceType", "Observation");
    obs.put("id", "vent-1");
    obs.put("status", "final");
    obs.putObject("code")
        .putArray("coding")
        .addObject()
        .put("system", "http://loinc.org")
        .put("code", FhirSofaMapper.LOINC_OXYGEN_DELIVERY_DEVICE)
        .put("display", "Oxygen delivery device");
    obs.putObject("valueCodeableConcept").put("text", "Invasive mechanical ventilation");

    ExtractResult result = FhirSofaMapper.extractValidated(obs);
    assertEquals(1, result.inputs.size());
    assertEquals(Component.RESPIRATION, result.inputs.get(0).name);
    assertEquals(Boolean.TRUE, result.inputs.get(0).mechanicallyVentilated);
    assertEquals("Observation/vent-1", result.inputs.get(0).evidenceIds.get(0));
    assertTrue(result.invalid.isEmpty());
  }

  @Test
  void mapsNorepinephrineRateWhenAlreadyWeightNormalized() {
    ObjectNode med = mapper.createObjectNode();
    med.put("resourceType", "MedicationAdministration");
    med.put("id", "norepi-1");
    med.put("status", "in-progress");
    med.putObject("medicationCodeableConcept").put("text", "Norepinephrine infusion");
    med.putObject("dosage").putObject("rateQuantity").put("value", 0.02).put("unit", "mcg/kg/min");

    ExtractResult result = FhirSofaMapper.extractValidated(med);
    assertEquals(1, result.inputs.size());
    assertEquals(Component.CARDIOVASCULAR, result.inputs.get(0).name);
    assertEquals("norepinephrine", result.inputs.get(0).vasopressorAgent);
    assertEquals(0.02, result.inputs.get(0).vasopressorDoseUgKgMin);
    assertTrue(result.invalid.isEmpty());
  }

  @Test
  void doesNotTreatVasopressinUnitsPerMinuteAsNorepinephrineDose() {
    ObjectNode med = mapper.createObjectNode();
    med.put("resourceType", "MedicationAdministration");
    med.put("id", "vaso-1");
    med.put("status", "in-progress");
    med.putObject("medicationCodeableConcept").put("text", "Vasopressin");
    med.putObject("dosage").putObject("rateQuantity").put("value", 0.03).put("unit", "units/min");

    ExtractResult result = FhirSofaMapper.extractValidated(med);
    assertEquals(1, result.inputs.size());
    assertEquals("vasopressin", result.inputs.get(0).vasopressorAgent);
    assertNull(result.inputs.get(0).vasopressorDoseUgKgMin);
    assertTrue(result.invalid.isEmpty());
  }
}
