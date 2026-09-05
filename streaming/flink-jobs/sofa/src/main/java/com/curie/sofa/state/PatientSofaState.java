package com.curie.sofa.state;

import com.curie.sofa.scoring.SofaScorer.Component;
import com.curie.sofa.scoring.SofaScorer.ComponentInput;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

/**
 * Per-patient encounter-scoped SOFA feature state.
 *
 * <p>Freshness is tracked <em>per clinical value</em>, not per component: a partial update writes
 * only the fields it carries and refreshes only their timestamps, so an old bilirubin is not
 * silently refreshed by a new platelets row. Older values for the same field are ignored
 * (late/out-of-order), but an older event may still carry the newest value for a different field.
 * Values expire per value class ({@link #VALUE_TTL_MS}) and drop their evidence when they do.
 */
public class PatientSofaState implements Serializable {

  /** Freshness windows per clinical value, in epoch millis (prototype defaults — not clinically
   * validated). Mirrors {@code eval/sofa/stream_scorer.py} {@code VALUE_TTL}. */
  public static final Map<String, Long> VALUE_TTL_MS = new HashMap<>();

  static {
    VALUE_TTL_MS.put("platelets10e9L", 24L * 3_600_000);
    VALUE_TTL_MS.put("bilirubinMgDl", 24L * 3_600_000);
    VALUE_TTL_MS.put("creatinineMgDl", 24L * 3_600_000);
    VALUE_TTL_MS.put("urineOutputMlDay", 24L * 3_600_000);
    VALUE_TTL_MS.put("pao2Fio2", 4L * 3_600_000);
    VALUE_TTL_MS.put("spo2Fio2", 4L * 3_600_000);
    VALUE_TTL_MS.put("pao2Mmhg", 4L * 3_600_000);
    VALUE_TTL_MS.put("spo2Percent", 4L * 3_600_000);
    VALUE_TTL_MS.put("fio2Fraction", 4L * 3_600_000);
    VALUE_TTL_MS.put("mechanicallyVentilated", 24L * 3_600_000);
    VALUE_TTL_MS.put("mapMmhg", 1L * 3_600_000);
    VALUE_TTL_MS.put("onVasopressors", 2L * 3_600_000);
    VALUE_TTL_MS.put("vasopressorAgent", 2L * 3_600_000);
    VALUE_TTL_MS.put("vasopressorDoseUgKgMin", 2L * 3_600_000);
    VALUE_TTL_MS.put("gcs", 6L * 3_600_000);
  }

  public String patientId;
  public String encounterId;
  public long lastEventTimeMs = Long.MIN_VALUE;
  public final Map<Component, Map<String, TimedValue>> values = new EnumMap<>(Component.class);
  public final Map<Component, Map<String, List<String>>> evidence = new EnumMap<>(Component.class);

  public static final class TimedValue implements Serializable {
    public Object value; // Double | Integer | Boolean | String
    public long eventTimeMs;

    public TimedValue() {}

    public TimedValue(Object value, long eventTimeMs) {
      this.value = value;
      this.eventTimeMs = eventTimeMs;
    }
  }

  /** @return true if any field was applied; false if the whole update was stale */
  public boolean apply(ComponentInput update, long eventTimeMs, long ingestTimeMs) {
    Map<String, TimedValue> slot = values.computeIfAbsent(update.name, k -> new HashMap<>());
    Map<String, List<String>> eslot = evidence.computeIfAbsent(update.name, k -> new HashMap<>());
    boolean changed = false;
    changed |= putField(slot, eslot, "pao2Fio2", update.pao2Fio2, eventTimeMs, update.evidenceIds);
    changed |= putField(slot, eslot, "spo2Fio2", update.spo2Fio2, eventTimeMs, update.evidenceIds);
    changed |=
        putField(slot, eslot, "spo2Percent", update.spo2Percent, eventTimeMs, update.evidenceIds);
    changed |= putField(slot, eslot, "pao2Mmhg", update.pao2Mmhg, eventTimeMs, update.evidenceIds);
    changed |=
        putField(slot, eslot, "fio2Fraction", update.fio2Fraction, eventTimeMs, update.evidenceIds);
    changed |=
        putField(
            slot,
            eslot,
            "mechanicallyVentilated",
            update.mechanicallyVentilated,
            eventTimeMs,
            update.evidenceIds);
    changed |=
        putField(
            slot, eslot, "platelets10e9L", update.platelets10e9L, eventTimeMs, update.evidenceIds);
    changed |=
        putField(slot, eslot, "bilirubinMgDl", update.bilirubinMgDl, eventTimeMs, update.evidenceIds);
    changed |= putField(slot, eslot, "mapMmhg", update.mapMmhg, eventTimeMs, update.evidenceIds);
    changed |=
        putField(
            slot, eslot, "onVasopressors", update.onVasopressors, eventTimeMs, update.evidenceIds);
    changed |=
        putField(
            slot,
            eslot,
            "vasopressorAgent",
            update.vasopressorAgent,
            eventTimeMs,
            update.evidenceIds);
    changed |=
        putField(
            slot,
            eslot,
            "vasopressorDoseUgKgMin",
            update.vasopressorDoseUgKgMin,
            eventTimeMs,
            update.evidenceIds);
    changed |= putField(slot, eslot, "gcs", update.gcs, eventTimeMs, update.evidenceIds);
    changed |=
        putField(
            slot,
            eslot,
            "creatinineMgDl",
            update.creatinineMgDl,
            eventTimeMs,
            update.evidenceIds);
    changed |=
        putField(
            slot,
            eslot,
            "urineOutputMlDay",
            update.urineOutputMlDay,
            eventTimeMs,
            update.evidenceIds);
    if (changed && eventTimeMs > lastEventTimeMs) {
      lastEventTimeMs = eventTimeMs;
    }
    return changed;
  }

  public void resetForEncounter(String newEncounterId) {
    values.clear();
    evidence.clear();
    lastEventTimeMs = Long.MIN_VALUE;
    encounterId = newEncounterId;
  }

  public List<ComponentInput> snapshotInputs() {
    return snapshotInputs(lastEventTimeMs);
  }

  public List<ComponentInput> snapshotInputs(long nowMs) {
    List<ComponentInput> out = new ArrayList<>();
    for (Component c : Component.values()) {
      ComponentInput in = new ComponentInput(c);
      Map<String, TimedValue> slot = values.get(c);
      if (slot != null) {
        LinkedHashSet<String> eids = new LinkedHashSet<>();
        for (Map.Entry<String, TimedValue> e : slot.entrySet()) {
          String key = e.getKey();
          TimedValue tv = e.getValue();
          Long ttl = VALUE_TTL_MS.get(key);
          if (nowMs != Long.MIN_VALUE && ttl != null && nowMs - tv.eventTimeMs > ttl) {
            continue; // expired value (and its evidence) drops out
          }
          assign(in, key, tv.value);
          List<String> ev = evidence.get(c) != null ? evidence.get(c).get(key) : null;
          if (ev != null) {
            eids.addAll(ev);
          }
        }
        in.evidenceIds.addAll(eids);
      }
      out.add(in);
    }
    return out;
  }

  private static boolean putField(
      Map<String, TimedValue> slot,
      Map<String, List<String>> eslot,
      String key,
      Object value,
      long eventTimeMs,
      List<String> evidenceIds) {
    if (value == null) {
      return false;
    }
    TimedValue prior = slot.get(key);
    if (prior != null && eventTimeMs < prior.eventTimeMs) {
      return false; // stale value for this field only
    }
    slot.put(key, new TimedValue(value, eventTimeMs));
    if (evidenceIds != null && !evidenceIds.isEmpty()) {
      eslot.put(key, new ArrayList<>(evidenceIds));
    }
    return true;
  }

  private static void assign(ComponentInput in, String key, Object value) {
    switch (key) {
      case "pao2Fio2" -> in.pao2Fio2 = (Double) value;
      case "spo2Fio2" -> in.spo2Fio2 = (Double) value;
      case "spo2Percent" -> in.spo2Percent = (Double) value;
      case "pao2Mmhg" -> in.pao2Mmhg = (Double) value;
      case "fio2Fraction" -> in.fio2Fraction = (Double) value;
      case "mechanicallyVentilated" -> in.mechanicallyVentilated = (Boolean) value;
      case "platelets10e9L" -> in.platelets10e9L = (Double) value;
      case "bilirubinMgDl" -> in.bilirubinMgDl = (Double) value;
      case "mapMmhg" -> in.mapMmhg = (Double) value;
      case "onVasopressors" -> in.onVasopressors = (Boolean) value;
      case "vasopressorAgent" -> in.vasopressorAgent = (String) value;
      case "vasopressorDoseUgKgMin" -> in.vasopressorDoseUgKgMin = (Double) value;
      case "gcs" -> in.gcs = (Integer) value;
      case "creatinineMgDl" -> in.creatinineMgDl = (Double) value;
      case "urineOutputMlDay" -> in.urineOutputMlDay = (Double) value;
      default -> throw new IllegalArgumentException("Unknown SOFA field: " + key);
    }
  }
}
