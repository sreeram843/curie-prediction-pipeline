"""Reference Kafka SOFA scorer (Python) — mirrors Flink naive alert path for local E2E.

Not a substitute for the Flink job in production posture; used for dry-runs and harnesses.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from typing import Any

import orjson

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


def _evidence_id(resource: dict[str, Any]) -> str | None:
    rtype = resource.get("resourceType")
    rid = resource.get("id")
    if rtype and rid:
        return f"{rtype}/{rid}"
    return None


def observation_to_input(resource: dict[str, Any]) -> SofaComponentInput | None:
    if resource.get("resourceType") != "Observation":
        return None
    code = _primary_code(resource)
    value = _numeric(resource)
    eid = _evidence_id(resource)
    evidence = [eid] if eid else []
    if code == LOINC_PLATELETS and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.COAGULATION, platelets_10e9_l=value, evidence_ids=evidence
        )
    if code == LOINC_BILIRUBIN and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.LIVER, bilirubin_mg_dl=value, evidence_ids=evidence
        )
    if code == LOINC_CREATININE and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.RENAL, creatinine_mg_dl=value, evidence_ids=evidence
        )
    if code == LOINC_GCS and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.CNS, gcs=int(value), evidence_ids=evidence
        )
    if code == LOINC_SPO2 and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.RESPIRATION, spo2_fio2=value / 0.21, evidence_ids=evidence
        )
    if code == LOINC_MAP and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.CARDIOVASCULAR, map_mmhg=value, evidence_ids=evidence
        )
    if code == LOINC_PAO2 and value is not None:
        return SofaComponentInput(
            name=SofaComponentName.RESPIRATION, pao2_fio2=value / 0.21, evidence_ids=evidence
        )
    return None


class PatientState:
    def __init__(self) -> None:
        self.encounter_id: str | None = None
        self.latest: dict[SofaComponentName, SofaComponentInput] = {}

    def apply(self, update: SofaComponentInput) -> None:
        existing = self.latest.get(update.name)
        if existing is None:
            self.latest[update.name] = update
            return
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

    def inputs(self) -> list[SofaComponentInput]:
        return [
            self.latest.get(name) or SofaComponentInput(name=name) for name in SofaComponentName
        ]


def alert_id(patient_id: str, score: int | None, event_time: datetime, version: str) -> str:
    raw = f"{patient_id}|{score}|{event_time.isoformat()}|{version}"
    return "alert-" + hashlib.md5(raw.encode()).hexdigest()


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
            update = observation_to_input(resource)
            if update is None or not patient_id:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            state = states.setdefault(patient_id, PatientState())
            if env.get("encounter_id"):
                state.encounter_id = env["encounter_id"]
            state.apply(update)
            event_time = datetime.fromisoformat(
                str(env.get("event_time")).replace("Z", "+00:00")
            )
            result = compute_sofa_score(
                patient_id=patient_id,
                encounter_id=state.encounter_id,
                event_time=event_time,
                inputs=state.inputs(),
                rule_bundle_id="sepsis-sofa",
                rule_version="0.1.0",
            )
            if result.completeness == ScoreCompleteness.INSUFFICIENT_DATA:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            tier = tier_for_score(result.total_score)
            if tier == AcuityTier.NONE:
                if args.max_messages and seen >= args.max_messages:
                    break
                continue
            alert = {
                "schema_version": "1.0.0",
                "alert_id": alert_id(
                    patient_id, result.total_score, event_time, result.rule_version
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
