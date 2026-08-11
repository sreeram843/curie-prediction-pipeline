package com.curie.sofa.fhir;

import com.curie.sofa.scoring.SofaScorer;
import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Optional;

/**
 * Maps FHIR Observation (and simple MedicationAdministration) payloads onto SOFA inputs.
 * LOINC codes are a pragmatic Synthea-oriented subset for the prototype.
 */
public final class FhirSofaMapper {

  // Common LOINC / Synthea-friendly codes
  public static final String LOINC_PLATELETS = "777-3";
  public static final String LOINC_BILIRUBIN = "1975-2";
  public static final String LOINC_CREATININE = "2160-0";
  public static final String LOINC_GCS = "9269-2";
  public static final String LOINC_SPO2 = "2708-6";
  public static final String LOINC_MAP = "8478-0";
  public static final String LOINC_SBP = "8480-6";
  public static final String LOINC_DBP = "8462-4";
  public static final String LOINC_PAO2 = "2703-7";

  private FhirSofaMapper() {}

  public static Optional<ComponentInput> fromObservation(JsonNode resource) {
    if (resource == null || !"Observation".equals(text(resource, "resourceType"))) {
      return Optional.empty();
    }
    String code = primaryCode(resource);
    if (code == null) {
      return Optional.empty();
    }
    Double value = numericValue(resource);
    String evidenceId = evidenceId(resource);
    return switch (code) {
      case LOINC_PLATELETS -> Optional.of(withEvidence(Component.COAGULATION, evidenceId, in -> in.platelets10e9L = value));
      case LOINC_BILIRUBIN -> Optional.of(withEvidence(Component.LIVER, evidenceId, in -> in.bilirubinMgDl = value));
      case LOINC_CREATININE -> Optional.of(withEvidence(Component.RENAL, evidenceId, in -> in.creatinineMgDl = value));
      case LOINC_GCS -> Optional.of(
          withEvidence(
              Component.CNS,
              evidenceId,
              in -> {
                if (value != null) {
                  in.gcs = value.intValue();
                }
              }));
      case LOINC_SPO2 -> Optional.of(
          withEvidence(
              Component.RESPIRATION,
              evidenceId,
              in -> {
                // Prototype proxy: SpO2% / assumed FiO2 0.21 → ratio-like value when FiO2 unknown
                if (value != null) {
                  in.spo2Fio2 = value / 0.21;
                }
              }));
      case LOINC_MAP -> Optional.of(withEvidence(Component.CARDIOVASCULAR, evidenceId, in -> in.mapMmhg = value));
      case LOINC_PAO2 -> Optional.of(
          withEvidence(
              Component.RESPIRATION,
              evidenceId,
              in -> {
                if (value != null) {
                  in.pao2Fio2 = value / 0.21;
                }
              }));
      default -> Optional.empty();
    };
  }

  public static Optional<ComponentInput> fromMedicationAdministration(JsonNode resource) {
    if (resource == null || !"MedicationAdministration".equals(text(resource, "resourceType"))) {
      return Optional.empty();
    }
    String display = medicationDisplay(resource).toLowerCase();
    if (display.contains("norepinephrine")
        || display.contains("epinephrine")
        || display.contains("vasopressin")
        || display.contains("dopamine")
        || display.contains("phenylephrine")) {
      ComponentInput in = new ComponentInput(Component.CARDIOVASCULAR);
      in.onVasopressors = true;
      in.evidenceIds.add(evidenceId(resource));
      return Optional.of(in);
    }
    return Optional.empty();
  }

  public static List<ComponentInput> extract(JsonNode resource) {
    List<ComponentInput> out = new ArrayList<>();
    fromObservation(resource).ifPresent(out::add);
    fromMedicationAdministration(resource).ifPresent(out::add);
    return out;
  }

  private interface Mutator {
    void apply(ComponentInput in);
  }

  private static ComponentInput withEvidence(Component name, String evidenceId, Mutator mutator) {
    ComponentInput in = new ComponentInput(name);
    mutator.apply(in);
    if (evidenceId != null) {
      in.evidenceIds.add(evidenceId);
    }
    return in;
  }

  private static String primaryCode(JsonNode resource) {
    JsonNode coding = resource.path("code").path("coding");
    if (!coding.isArray()) {
      return null;
    }
    for (JsonNode c : coding) {
      String code = text(c, "code");
      if (code != null) {
        return code;
      }
    }
    return null;
  }

  private static Double numericValue(JsonNode resource) {
    JsonNode qty = resource.get("valueQuantity");
    if (qty != null && qty.has("value") && qty.get("value").isNumber()) {
      return qty.get("value").asDouble();
    }
    if (resource.has("valueInteger") && resource.get("valueInteger").isNumber()) {
      return resource.get("valueInteger").asDouble();
    }
    return null;
  }

  private static String medicationDisplay(JsonNode resource) {
    JsonNode concept = resource.path("medicationCodeableConcept");
    String text = text(concept, "text");
    if (text != null) {
      return text;
    }
    JsonNode coding = concept.path("coding");
    if (coding.isArray()) {
      Iterator<JsonNode> it = coding.elements();
      while (it.hasNext()) {
        JsonNode c = it.next();
        String display = text(c, "display");
        if (display != null) {
          return display;
        }
      }
    }
    return "";
  }

  private static String evidenceId(JsonNode resource) {
    String type = text(resource, "resourceType");
    String id = text(resource, "id");
    if (type != null && id != null) {
      return type + "/" + id;
    }
    return null;
  }

  private static String text(JsonNode node, String field) {
    if (node == null || !node.has(field) || node.get(field).isNull()) {
      return null;
    }
    return node.get(field).asText();
  }
}
