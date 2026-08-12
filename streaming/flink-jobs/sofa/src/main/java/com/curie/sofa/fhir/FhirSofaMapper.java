package com.curie.sofa.fhir;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Maps FHIR Observation / MedicationAdministration onto SOFA inputs with unit/status validation.
 * Invalid resources are returned with a reason for DLQ — never silently scored.
 */
public final class FhirSofaMapper {

  public static final String LOINC_PLATELETS = "777-3";
  public static final String LOINC_BILIRUBIN = "1975-2";
  public static final String LOINC_CREATININE = "2160-0";
  public static final String LOINC_GCS = "9269-2";
  public static final String LOINC_SPO2 = "2708-6";
  public static final String LOINC_MAP = "8478-0";
  public static final String LOINC_PAO2 = "2703-7";
  public static final String LOINC_FIO2 = "3150-0";

  private static final Set<String> USABLE_STATUS =
      Set.of("final", "amended", "corrected", "preliminary");

  private FhirSofaMapper() {}

  public static final class ExtractResult implements Serializable {
    public final List<ComponentInput> inputs = new ArrayList<>();
    public final List<InvalidEvent> invalid = new ArrayList<>();
  }

  public static final class InvalidEvent implements Serializable {
    public String reason;
    public String resourceType;
    public String resourceId;
    public String code;
    public String unit;
    public String status;

    public InvalidEvent(String reason, JsonNode resource, String code, String unit, String status) {
      this.reason = reason;
      this.resourceType = text(resource, "resourceType");
      this.resourceId = text(resource, "id");
      this.code = code;
      this.unit = unit;
      this.status = status;
    }
  }

  public static ExtractResult extractValidated(JsonNode resource) {
    ExtractResult out = new ExtractResult();
    if (resource == null) {
      return out;
    }
    String type = text(resource, "resourceType");
    if ("Observation".equals(type)) {
      mapObservation(resource, out);
    } else if ("MedicationAdministration".equals(type)) {
      mapMedication(resource, out);
    }
    return out;
  }

  /** Backward-compatible: valid inputs only. */
  public static List<ComponentInput> extract(JsonNode resource) {
    return extractValidated(resource).inputs;
  }

  private static void mapObservation(JsonNode resource, ExtractResult out) {
    String status = text(resource, "status");
    if (status != null && !USABLE_STATUS.contains(status.toLowerCase(Locale.ROOT))) {
      out.invalid.add(
          new InvalidEvent("invalid_status:" + status, resource, primaryCode(resource), null, status));
      return;
    }
    String code = primaryCode(resource);
    if (code == null) {
      out.invalid.add(new InvalidEvent("missing_code", resource, null, null, status));
      return;
    }
    Double value = numericValue(resource);
    String unit = unit(resource);
    String evidenceId = evidenceId(resource);

    switch (code) {
      case LOINC_PLATELETS -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        Double platelets = normalizePlatelets(value, unit);
        if (platelets == null) {
          out.invalid.add(new InvalidEvent("invalid_unit", resource, code, unit, status));
          return;
        }
        out.inputs.add(
            withEvidence(Component.COAGULATION, evidenceId, in -> in.platelets10e9L = platelets));
      }
      case LOINC_BILIRUBIN -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        if (!unitAllowed(unit, "mg/dL", "mg/dl")) {
          out.invalid.add(new InvalidEvent("invalid_unit", resource, code, unit, status));
          return;
        }
        out.inputs.add(withEvidence(Component.LIVER, evidenceId, in -> in.bilirubinMgDl = value));
      }
      case LOINC_CREATININE -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        if (!unitAllowed(unit, "mg/dL", "mg/dl")) {
          out.invalid.add(new InvalidEvent("invalid_unit", resource, code, unit, status));
          return;
        }
        out.inputs.add(withEvidence(Component.RENAL, evidenceId, in -> in.creatinineMgDl = value));
      }
      case LOINC_GCS -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        int gcs = value.intValue();
        if (gcs < 3 || gcs > 15) {
          out.invalid.add(new InvalidEvent("invalid_gcs_range", resource, code, unit, status));
          return;
        }
        out.inputs.add(withEvidence(Component.CNS, evidenceId, in -> in.gcs = gcs));
      }
      case LOINC_SPO2 -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        if (!unitAllowed(unit, "%", "percent", null)) {
          out.invalid.add(new InvalidEvent("invalid_unit", resource, code, unit, status));
          return;
        }
        // Store raw SpO2 — ratio requires FiO2 (no ambient-air assumption).
        out.inputs.add(
            withEvidence(Component.RESPIRATION, evidenceId, in -> in.spo2Percent = value));
      }
      case LOINC_MAP -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        if (!unitAllowed(unit, "mmHg", "mm[Hg]", "mmhg")) {
          out.invalid.add(new InvalidEvent("invalid_unit", resource, code, unit, status));
          return;
        }
        out.inputs.add(withEvidence(Component.CARDIOVASCULAR, evidenceId, in -> in.mapMmhg = value));
      }
      case LOINC_PAO2 -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        if (!unitAllowed(unit, "mmHg", "mm[Hg]", "mmhg")) {
          out.invalid.add(new InvalidEvent("invalid_unit", resource, code, unit, status));
          return;
        }
        out.inputs.add(
            withEvidence(Component.RESPIRATION, evidenceId, in -> in.pao2Mmhg = value));
      }
      case LOINC_FIO2 -> {
        if (value == null) {
          out.invalid.add(new InvalidEvent("missing_value", resource, code, unit, status));
          return;
        }
        double frac = value > 1.0 ? value / 100.0 : value;
        if (frac <= 0 || frac > 1.0) {
          out.invalid.add(new InvalidEvent("invalid_fio2_range", resource, code, unit, status));
          return;
        }
        out.inputs.add(
            withEvidence(Component.RESPIRATION, evidenceId, in -> in.fio2Fraction = frac));
      }
      default -> {
        // Unknown LOINC — ignore quietly (not an error)
      }
    }
  }

  private static void mapMedication(JsonNode resource, ExtractResult out) {
    String display = medicationDisplay(resource).toLowerCase(Locale.ROOT);
    if (display.contains("norepinephrine")
        || display.contains("epinephrine")
        || display.contains("vasopressin")
        || display.contains("dopamine")
        || display.contains("phenylephrine")
        || display.contains("dobutamine")) {
      ComponentInput in = new ComponentInput(Component.CARDIOVASCULAR);
      in.onVasopressors = true;
      if (display.contains("norepinephrine")) {
        in.vasopressorAgent = "norepinephrine";
      } else if (display.contains("epinephrine")) {
        in.vasopressorAgent = "epinephrine";
      } else if (display.contains("dopamine")) {
        in.vasopressorAgent = "dopamine";
      } else if (display.contains("dobutamine")) {
        in.vasopressorAgent = "dobutamine";
      } else {
        in.vasopressorAgent = "other";
      }
      String eid = evidenceId(resource);
      if (eid != null) {
        in.evidenceIds.add(eid);
      }
      out.inputs.add(in);
    }
  }

  private static boolean unitAllowed(String unit, String... allowed) {
    if (unit == null || unit.isBlank()) {
      // Missing unit: fail closed for labs that require it
      for (String a : allowed) {
        if (a == null) {
          return true; // explicitly allow missing
        }
      }
      return false;
    }
    String u = unit.trim();
    for (String a : allowed) {
      if (a != null && a.equalsIgnoreCase(u)) {
        return true;
      }
    }
    return false;
  }

  /**
   * Normalize platelet count to 10^9/L. Accepts SI and common US lab units; bare {@code /uL} is
   * converted when the value looks like an absolute count (&gt;1000).
   */
  static Double normalizePlatelets(double value, String unit) {
    if (unit == null || unit.isBlank()) {
      return null;
    }
    String u = unit.trim();
    if (unitAllowed(u, "10*9/L", "10^9/L", "x10^9/L", "10*3/uL", "10^3/uL", "K/uL")) {
      return value;
    }
    if ("/uL".equalsIgnoreCase(u) || "uL".equalsIgnoreCase(u) || "1/uL".equalsIgnoreCase(u)) {
      if (value > 1000) {
        return value / 1000.0;
      }
      // Ambiguous small /uL values — reject rather than mis-score
      return null;
    }
    return null;
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

  private static String unit(JsonNode resource) {
    JsonNode qty = resource.get("valueQuantity");
    if (qty == null) {
      return null;
    }
    String u = text(qty, "unit");
    if (u != null) {
      return u;
    }
    return text(qty, "code");
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
