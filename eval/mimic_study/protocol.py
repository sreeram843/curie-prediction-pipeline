"""MIMIC-IV study protocol freeze (CURIE-014).

Machine-readable guardrails so the locked temporal test split cannot be used
for sweep / tuning / operating-point selection.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROTOCOL_PATH = (
    Path(__file__).resolve().parent / "frozen" / "protocol.v1.json"
)

# Commands that mutate or select operating points — never allowed on test.
TUNING_COMMANDS = frozenset(
    {
        "sweep",
        "tune",
        "grid_search",
        "threshold_search",
        "operating_point_selection",
        "ablation_design",
        "feature_debug",
    }
)

# Aliases that must resolve to the locked holdout role.
TEST_SPLIT_ALIASES = frozenset(
    {
        "test",
        "holdout",
        "temporal_holdout",
        "locked_holdout",
        "set_test",
        "mimic_test",
    }
)


class ProtocolError(ValueError):
    """Protocol violation (e.g. tuning on the locked test split)."""


@lru_cache(maxsize=1)
def load_protocol(path: str | None = None) -> dict[str, Any]:
    """Load the frozen protocol JSON."""
    target = Path(path) if path else PROTOCOL_PATH
    data = json.loads(target.read_text())
    if data.get("protocol_id") != "mimic-iv-governance-study.v1":
        raise ProtocolError(f"Unexpected protocol_id in {target}")
    if data.get("status") != "frozen":
        raise ProtocolError(f"Protocol is not frozen: {data.get('status')!r}")
    return data


def normalize_split_id(split_id: str) -> str:
    raw = (split_id or "").strip().lower().replace("-", "_")
    if raw in TEST_SPLIT_ALIASES:
        return "test"
    if raw in {"dev", "develop", "train", "training", "development"}:
        return "development"
    if raw in {"cal", "calib", "validation", "val", "calibration"}:
        return "calibration"
    return raw


def split_role(split_id: str, protocol: dict[str, Any] | None = None) -> str:
    proto = protocol or load_protocol()
    sid = normalize_split_id(split_id)
    splits = proto.get("splits") or {}
    block = splits.get(sid)
    if not isinstance(block, dict):
        raise ProtocolError(f"Unknown study split: {split_id!r}")
    return str(block.get("role") or "")


def assert_command_allowed_on_split(
    split_id: str,
    command: str,
    *,
    protocol: dict[str, Any] | None = None,
) -> None:
    """Raise ProtocolError if ``command`` is forbidden on ``split_id``.

    Acceptance (CURIE-014): the test split cannot be used by sweep/tuning.
    """
    proto = protocol or load_protocol()
    sid = normalize_split_id(split_id)
    cmd = (command or "").strip().lower()
    splits = proto.get("splits") or {}
    block = splits.get(sid)
    if not isinstance(block, dict):
        raise ProtocolError(f"Unknown study split: {split_id!r}")

    forbidden = {
        str(x).strip().lower() for x in (block.get("forbidden_commands") or [])
    }
    if cmd in forbidden or (sid == "test" and cmd in TUNING_COMMANDS):
        raise ProtocolError(
            f"Command {command!r} is forbidden on locked split {sid!r} "
            f"(protocol {proto.get('protocol_id')}). "
            "Tune on development; select on calibration; evaluate once on test."
        )

    allowed = block.get("allowed_commands")
    if allowed is not None:
        allowed_set = {str(x).strip().lower() for x in allowed}
        # Tuning commands must be explicitly allowed; eval commands may be listed.
        if cmd in TUNING_COMMANDS and cmd not in allowed_set:
            raise ProtocolError(
                f"Command {command!r} is not allowed on split {sid!r}"
            )


def assert_split_allowed_for_tuning(
    split_id: str,
    *,
    command: str = "sweep",
    protocol: dict[str, Any] | None = None,
) -> None:
    """Convenience guard for sweep / grid / threshold search entrypoints."""
    assert_command_allowed_on_split(split_id, command, protocol=protocol)


def primary_endpoint(protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    proto = protocol or load_protocol()
    pe = proto.get("primary_endpoint")
    if not isinstance(pe, dict) or not pe.get("id"):
        raise ProtocolError("Protocol missing primary_endpoint")
    return pe


def operating_point_selection_rule(
    protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proto = protocol or load_protocol()
    ops = proto.get("operating_point_selection")
    if not isinstance(ops, dict) or not ops.get("rule"):
        raise ProtocolError("Protocol missing operating_point_selection.rule")
    if not ops.get("forbidden_on_test", False):
        raise ProtocolError("operating_point_selection must forbid test")
    return ops


def claims_evidence_map(protocol: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    proto = protocol or load_protocol()
    rows = proto.get("product_claims_evidence_map")
    if not isinstance(rows, list) or not rows:
        raise ProtocolError("Protocol missing product_claims_evidence_map")
    return list(rows)


def protocol_summary(protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compact summary for CLI / docs checks."""
    proto = protocol or load_protocol()
    pe = primary_endpoint(proto)
    ops = operating_point_selection_rule(proto)
    return {
        "protocol_id": proto["protocol_id"],
        "status": proto["status"],
        "primary_endpoint_id": pe["id"],
        "primary_success_rule": pe["success_rule"],
        "operating_point_rule": ops["rule"],
        "test_forbidden_commands": list(
            (proto.get("splits") or {}).get("test", {}).get("forbidden_commands")
            or []
        ),
        "claims": [
            {"claim_id": c["claim_id"], "status": c["status"]}
            for c in claims_evidence_map(proto)
        ],
    }
