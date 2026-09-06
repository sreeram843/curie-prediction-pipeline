"""Reference Kafka SOFA scorer (Python) — mirrors Flink naive alert path for local E2E.

Not a substitute for the Flink job in production posture; used for dry-runs and harnesses.
"""

from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import Any

import orjson

from eval.sofa.alert_ids import alert_id as canonical_alert_id
from eval.sofa.scoring import (
    AcuityTier,
    ScoreCompleteness,
    SofaComponentInput,
    SofaComponentName,
    compute_sofa_score,
    tier_for_score,
)

# LOINC codes aligned with FhirSofaMapper
LOINC_PLATELETS = "777-3"
LOINC_BILIRUBIN = "1975-2"
LOINC_CREATININE = "2160-0"
LOINC_GCS = "9269-2"
LOINC_SPO2 = "2708-6"
LOINC_MAP = "8478-0"
LOINC_PAO2 = "2703-7"
LOINC_FIO2 = "3150-0"

USABLE_STATUS = frozenset({"final", "amended", "corrected", "preliminary"})
IDEMPOTENCY_TTL = timedelta(hours=24)
IDEMPOTENCY_MAX_KEYS = 10_000

# Per-clinical-value freshness windows for the streaming state (prototype
# defaults — not clinically validated). A value older than its window at the
# last event time is dropped from the snapshot (fail closed: the component
# becomes missing rather than scoring a stale measurement).
VALUE_TTL: dict[str, timedelta] = {
    # labs — daily cadence
    "platelets_10e9_l": timedelta(hours=24),
    "bilirubin_mg_dl": timedelta(hours=24),
    "creatinine_mg_dl": timedelta(hours=24),
    "urine_output_ml_day": timedelta(hours=24),
    # respiration — intermittent charting/gases
    "pao2_fio2": timedelta(hours=4),
    "spo2_fio2": timedelta(hours=4),
    "pao2_mmhg": timedelta(hours=4),
    "spo2_percent": timedelta(hours=4),
    "fio2_fraction": timedelta(hours=4),
    "mechanically_ventilated": timedelta(hours=24),
    # cardiovascular — beat-to-beat-derived, short-lived
    "map_mmhg": timedelta(hours=1),
    "on_vasopressors": timedelta(hours=2),
    "vasopressor_agent": timedelta(hours=2),
    "vasopressor_dose_ug_kg_min": timedelta(hours=2),
    # CNS
    "gcs": timedelta(hours=6),
}


def effective_availability_time(envelope: dict[str, Any]) -> datetime:
    """Return the leakage-safe evaluation clock for a canonical envelope."""
    for key in ("availability_time", "ingest_time", "event_time"):
        raw = envelope.get(key)
        if raw is None or not str(raw).strip():
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid {key}: {raw}") from exc
    raise ValueError("missing event_time")


def _primary_code(resource: dict[str, Any]) -> str | None:
    for coding in (resource.get("code") or {}).get("coding") or []:
        if coding.get("code"):
            return str(coding["code"])
    return None


def _numeric(resource: dict[str, Any]) -> float | None:
    qty = resource.get("valueQuantity") or {}
    if "value" in qty:
        return float(qty["value"])
    if "valueInteger" in resource:
        return float(resource["valueInteger"])
    return None


def _unit(resource: dict[str, Any]) -> str | None:
    qty = resource.get("valueQuantity") or {}
    return qty.get("unit") or qty.get("code")


def _evidence_id(resource: dict[str, Any]) -> str | None:
    rtype = resource.get("resourceType")
    rid = resource.get("id")
    if rtype and rid:
        return f"{rtype}/{rid}"
    return None


def _unit_ok(unit: str | None, *allowed: str | None) -> bool:
    if unit is None or not str(unit).strip():
        return None in allowed
    u = str(unit).strip()
    return any(a is not None and a.lower() == u.lower() for a in allowed)


def _normalize_platelets(value: float, unit: str | None) -> float | None:
    if _unit_ok(unit, "10*9/L", "10^9/L", "x10^9/L", "10*3/uL", "10^3/uL", "K/uL"):
        return value
    if unit and unit.strip().lower() in {"/ul", "ul", "1/ul"}:
        if value > 1000:
            return value / 1000.0
        return None
    return None


def observation_to_input(resource: dict[str, Any]) -> SofaComponentInput | None:
    """Map Observation → SOFA input; returns None when invalid/unsupported (fail closed)."""
    if resource.get("resourceType") != "Observation":
        return None
    status = resource.get("status")
    if status is not None and str(status).lower() not in USABLE_STATUS:
        return None
    code = _primary_code(resource)
    value = _numeric(resource)
    unit = _unit(resource)
    eid = _evidence_id(resource)
    evidence = [eid] if eid else []
    if code == LOINC_PLATELETS and value is not None:
        platelets = _normalize_platelets(value, unit)
        if platelets is None:
            return None
        return SofaComponentInput(
            name=SofaComponentName.COAGULATION,
            platelets_10e9_l=platelets,
            evidence_ids=evidence,
        )
    if code == LOINC_BILIRUBIN and value is not None:
        if not _unit_ok(unit, "mg/dL", "mg/dl"):
            return None
        return SofaComponentInput(
            name=SofaComponentName.LIVER, bilirubin_mg_dl=value, evidence_ids=evidence
        )
    if code == LOINC_CREATININE and value is not None:
        if not _unit_ok(unit, "mg/dL", "mg/dl"):
            return None
        return SofaComponentInput(
            name=SofaComponentName.RENAL, creatinine_mg_dl=value, evidence_ids=evidence
        )
    if code == LOINC_GCS and value is not None:
        gcs = int(value)
        if gcs < 3 or gcs > 15:
            return None
        return SofaComponentInput(
            name=SofaComponentName.CNS, gcs=gcs, evidence_ids=evidence
        )
    if code == LOINC_SPO2 and value is not None:
        if not _unit_ok(unit, "%", "percent", None):
            return None
        return SofaComponentInput(
            name=SofaComponentName.RESPIRATION, spo2_percent=value, evidence_ids=evidence
        )
    if code == LOINC_MAP and value is not None:
        if not _unit_ok(unit, "mmHg", "mm[Hg]", "mmhg"):
            return None
        return SofaComponentInput(
            name=SofaComponentName.CARDIOVASCULAR, map_mmhg=value, evidence_ids=evidence
        )
    if code == LOINC_PAO2 and value is not None:
        if not _unit_ok(unit, "mmHg", "mm[Hg]", "mmhg"):
            return None
        return SofaComponentInput(
            name=SofaComponentName.RESPIRATION, pao2_mmhg=value, evidence_ids=evidence
        )
    if code == LOINC_FIO2 and value is not None:
        frac = value / 100.0 if value > 1.0 else value
        if frac <= 0 or frac > 1.0:
            return None
        return SofaComponentInput(
            name=SofaComponentName.RESPIRATION, fio2_fraction=frac, evidence_ids=evidence
        )
    return None


class IdempotencyCache:
    """TTL + capacity-bounded idempotency (mirrors Java IdempotencyCache)."""

    def __init__(
        self,
        ttl: timedelta = IDEMPOTENCY_TTL,
        max_keys: int = IDEMPOTENCY_MAX_KEYS,
    ) -> None:
        self.ttl = ttl
        self.max_keys = max_keys
        self._entries: OrderedDict[str, datetime] = OrderedDict()

    def seen(self, key: str | None, now: datetime | None = None) -> bool:
        if not key:
            return False
        now = now or datetime.now(tz=UTC)
        self._prune(now)
        prior = self._entries.get(key)
        if prior is not None and now - prior < self.ttl:
            return True
        self._entries[key] = now
        while len(self._entries) > self.max_keys:
            self._entries.popitem(last=False)
        return False

    def _prune(self, now: datetime) -> None:
        expired = [k for k, t in self._entries.items() if now - t >= self.ttl]
        for k in expired:
            del self._entries[k]


class PatientState:
    """Encounter-scoped, event-time ordered feature state with idempotency.

    Freshness is tracked **per clinical value**, not per component: a partial
    update writes only the fields it carries and refreshes only their
    timestamps, so an old bilirubin is not silently refreshed by a new
    platelets row. Values expire per value class (:data:`VALUE_TTL`) and drop
    their evidence when they do.
    """

    def __init__(self) -> None:
        self.encounter_id: str | None = None
        self.idempotency = IdempotencyCache()
        self._values: dict[SofaComponentName, dict[str, tuple[Any, datetime]]] = {}
        self._evidence: dict[SofaComponentName, dict[str, list[str]]] = {}
        self.last_event_time: datetime | None = None
        # Merged per-component view (no expiry) — compatibility surface for
        # harness/reliability callers; scoring uses inputs() (expiry applies).
        self.latest: dict[SofaComponentName, SofaComponentInput] = {}

    def seen(self, idempotency_key: str | None, now: datetime | None = None) -> bool:
        return self.idempotency.seen(idempotency_key, now)

    def set_encounter(self, encounter_id: str | None) -> None:
        if encounter_id and self.encounter_id and encounter_id != self.encounter_id:
            self._values.clear()
            self._evidence.clear()
            self.latest.clear()
            self.last_event_time = None
        if encounter_id:
            self.encounter_id = encounter_id

    def _merge_latest(self, update: SofaComponentInput) -> None:
        existing = self.latest.get(update.name)
        if existing is None:
            self.latest[update.name] = update.model_copy(deep=True)
            return
        data = existing.model_dump()
        for k, v in update.model_dump().items():
            if k == "name":
                continue
            if k == "evidence_ids":
                data["evidence_ids"] = list(
                    dict.fromkeys([*data["evidence_ids"], *v])
                )
            elif v is not None:
                data[k] = v
        self.latest[update.name] = SofaComponentInput.model_validate(data)

    def apply(self, update: SofaComponentInput, event_time: datetime) -> bool:
        data = update.model_dump()
        new_evidence = list(update.evidence_ids)
        slot = self._values.setdefault(update.name, {})
        eslot = self._evidence.setdefault(update.name, {})
        changed = False
        for key in VALUE_TTL:
            value = data.get(key)
            if value is None:
                continue
            prior = slot.get(key)
            if prior is not None and event_time < prior[1]:
                continue  # stale value for this field only
            slot[key] = (value, event_time)
            if new_evidence:
                eslot[key] = new_evidence
            changed = True
        if changed:
            self._merge_latest(update)
            if self.last_event_time is None or event_time > self.last_event_time:
                self.last_event_time = event_time
        return changed

    def inputs(self, as_of: datetime | None = None) -> list[SofaComponentInput]:
        now = as_of or self.last_event_time
        out: list[SofaComponentInput] = []
        for name in SofaComponentName:
            kwargs: dict[str, Any] = {"name": name}
            evidence: list[str] = []
            for key, (value, observed_at) in self._values.get(name, {}).items():
                ttl = VALUE_TTL.get(key)
                if now is not None and ttl is not None and (now - observed_at) > ttl:
                    continue  # expired value (and its evidence) drops out
                kwargs[key] = value
                evidence.extend(self._evidence.get(name, {}).get(key, []))
            kwargs["evidence_ids"] = list(dict.fromkeys(evidence))
            out.append(SofaComponentInput.model_validate(kwargs))
        return out


def alert_id(
    patient_id: str,
    score: int | None,
    event_time: datetime,
    version: str,
    *,
    encounter_id: str | None = None,
    indicator: str = "sofa-deterioration",
) -> str:
    event_time_ms = int(event_time.timestamp() * 1000)
    return canonical_alert_id(
        patient_id, encounter_id, indicator, score, event_time_ms, version
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reference SOFA Kafka scorer")
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--group", default="curie-sofa-python-ref")
    parser.add_argument("--max-messages", type=int, default=0, help="0 = run forever")
    args = parser.parse_args(argv)

    try:
        from confluent_kafka import Consumer, Producer
    except ImportError:
        print("pip install -e '.[kafka]'", file=sys.stderr)
        return 1

    consumer = Consumer(
        {
            "bootstrap.servers": args.bootstrap,
            "group.id": args.group,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe(["observations", "medications"])
    producer = Producer({"bootstrap.servers": args.bootstrap})
    states: dict[str, PatientState] = {}
    emitted = 0
    seen = 0

    print(f"Listening on {args.bootstrap} (ctrl-c to stop)...")
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(msg.error(), file=sys.stderr)
                continue
            seen += 1
            env = orjson.loads(msg.value())
            patient_id = env.get("patient_id")
            resource = env.get("resource") or {}
            if not patient_id:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            state = states.setdefault(patient_id, PatientState())
            if state.seen(env.get("idempotency_key")):
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            update = observation_to_input(resource)
            if update is None:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            state.set_encounter(env.get("encounter_id"))
            event_time = datetime.fromisoformat(
                str(env.get("event_time")).replace("Z", "+00:00")
            )
            availability_time = effective_availability_time(env)
            if not state.apply(update, event_time):
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            from eval.indicators.registry import load_rule_bundle

            bundle = load_rule_bundle("sepsis-sofa")
            result = compute_sofa_score(
                patient_id=patient_id,
                encounter_id=state.encounter_id,
                event_time=availability_time,
                inputs=state.inputs(),
                rule_bundle_id=bundle["bundle_id"],
                rule_version=bundle["version"],
            )
            if result.completeness == ScoreCompleteness.INSUFFICIENT_DATA:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            threshold = int(bundle["alert"]["naive_threshold"])
            bands = bundle["alert"].get("severity_bands")
            tier = tier_for_score(
                result.total_score, naive_threshold=threshold, severity_bands=bands
            )
            if tier == AcuityTier.NONE:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            alert = {
                "schema_version": "1.0.0",
                "alert_id": alert_id(
                    patient_id,
                    result.total_score,
                    availability_time,
                    result.rule_version,
                    encounter_id=state.encounter_id,
                ),
                "patient_id": patient_id,
                "encounter_id": state.encounter_id,
                "indicator": "sofa-deterioration",
                "event_time": event_time.isoformat(),
                "clinical_event_time": event_time.isoformat(),
                "availability_time": availability_time.isoformat(),
                "ingest_time": datetime.now(UTC).isoformat(),
                "score": result.total_score,
                "completeness": result.completeness.value,
                "tier": tier.value,
                "component_breakdown": [c.model_dump(mode="json") for c in result.components],
                "missing_components": [m.value for m in result.missing_components],
                "evidence_ids": result.evidence_ids,
                "rule_bundle_id": result.rule_bundle_id,
                "rule_version": result.rule_version,
                "governance_path": "naive",
                "suppressed": False,
                "suppression_reason": None,
            }
            producer.produce("alerts", key=patient_id.encode(), value=orjson.dumps(alert))
            producer.poll(0)
            emitted += 1
            print(f"alert {alert['alert_id']} score={alert['score']} tier={alert['tier']}")
            if args.max_messages and seen >= args.max_messages:
                break
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush()
        consumer.close()
    print(f"Done. seen={seen} alerts={emitted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
