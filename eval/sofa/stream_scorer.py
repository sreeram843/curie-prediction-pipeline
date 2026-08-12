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
    """Encounter-scoped, event-time ordered feature state with idempotency."""

    def __init__(self) -> None:
        self.encounter_id: str | None = None
        self.latest: dict[SofaComponentName, SofaComponentInput] = {}
        self.component_event_time: dict[SofaComponentName, datetime] = {}
        self.idempotency = IdempotencyCache()

    def seen(self, idempotency_key: str | None, now: datetime | None = None) -> bool:
        return self.idempotency.seen(idempotency_key, now)

    def set_encounter(self, encounter_id: str | None) -> None:
        if encounter_id and self.encounter_id and encounter_id != self.encounter_id:
            self.latest.clear()
            self.component_event_time.clear()
        if encounter_id:
            self.encounter_id = encounter_id

    def apply(self, update: SofaComponentInput, event_time: datetime) -> bool:
        existing_t = self.component_event_time.get(update.name)
        if existing_t is not None and event_time < existing_t:
            return False
        existing = self.latest.get(update.name)
        if existing is None:
            self.latest[update.name] = update
            self.component_event_time[update.name] = event_time
            return True
        data = existing.model_dump()
        for k, v in update.model_dump().items():
            if k == "name":
                continue
            if k == "evidence_ids":
                merged = list(dict.fromkeys([*data["evidence_ids"], *v]))
                data["evidence_ids"] = merged
            elif v is not None:
                data[k] = v
        self.latest[update.name] = SofaComponentInput.model_validate(data)
        self.component_event_time[update.name] = event_time
        return True

    def inputs(self) -> list[SofaComponentInput]:
        return [
            self.latest.get(name) or SofaComponentInput(name=name) for name in SofaComponentName
        ]


def alert_id(
    patient_id: str,
    score: int | None,
    event_time: datetime,
    version: str,
    *,
    encounter_id: str | None = None,
    indicator: str = "sepsis",
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
            if not state.apply(update, event_time):
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            from eval.indicators.registry import load_rule_bundle

            bundle = load_rule_bundle("sepsis-sofa")
            result = compute_sofa_score(
                patient_id=patient_id,
                encounter_id=state.encounter_id,
                event_time=event_time,
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
                    event_time,
                    result.rule_version,
                    encounter_id=state.encounter_id,
                ),
                "patient_id": patient_id,
                "encounter_id": state.encounter_id,
                "indicator": "sepsis",
                "event_time": event_time.isoformat(),
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
