"""Investor claims matrix (CURIE-021).

Categories: demonstrated | under_evaluation | not_claimed
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

ClaimStatus = Literal["demonstrated", "under_evaluation", "not_claimed"]

FROZEN_DIR = Path(__file__).resolve().parent / "frozen"
CLAIMS_PATH = FROZEN_DIR / "claims_matrix.v1.json"

CLAIMS: list[dict[str, Any]] = [
    {
        "id": "DET-STREAM",
        "claim": "Deterministic multi-indicator scoring with versioned rule bundles and evidence IDs",  # noqa: E501
        "status": "demonstrated",
        "evidence": [
            "Golden fixtures / parity tests",
            "Dashboard evidence inspector",
            "Rule bundle hashes on alerts",
        ],
    },
    {
        "id": "GOV-VOLUME",
        "claim": "Shared governance reduces interruptive volume vs naive thresholding while preserving detection on offline evals",  # noqa: E501
        "status": "demonstrated",
        "evidence": [
            "Challenge 2019 setA/setB operating point",
            "Investor demo naive/passive/interruptive counts",
            "Manuscript claim tier: alert_policy_utility",
        ],
    },
    {
        "id": "EPISODE-ARB",
        "claim": "Multiple correlated signals aggregate into one patient episode with dominant problem + page arbitration",  # noqa: E501
        "status": "demonstrated",
        "evidence": [
            "CURIE-012 arbiter + fixtures",
            "Elena Vargas / Aisha Rahman demo patients",
            "Investor demo timeline → single episode",
        ],
    },
    {
        "id": "RELIABILITY",
        "claim": "Duplicate delivery, out-of-order events, and process restart do not corrupt alert/episode identity",  # noqa: E501
        "status": "under_evaluation",
        "evidence": [
            "Replay harness chaos tests",
            "Durable SQLite store restart tests",
            "Investor demo chaos scenarios",
            "Episode IDs now deterministic; strengthen chaos to assert ID equality before promoting",  # noqa: E501
        ],
    },
    {
        "id": "CDS-BOUNDARY",
        "claim": "CDS Hooks / FHIR evidence presentation boundary without rescoring",
        "status": "demonstrated",
        "evidence": ["CURIE-019 cds-hooks + fhir-evidence endpoints"],
    },
    {
        "id": "OPS-SEC",
        "claim": "Production-shaped auth/CORS, ops status, and kill switches",
        "status": "demonstrated",
        "evidence": ["CURIE-018 security-observability"],
    },
    {
        "id": "MIMIC-STAGE-B",
        "claim": "MIMIC-IV Stage B clinical retrospective with locked temporal holdout",
        "status": "under_evaluation",
        "evidence": [
            "Protocol frozen (CURIE-014)",
            "Demo-schema harness only until PhysioNet extract under DUA",
        ],
    },
    {
        "id": "SHADOW-PROD",
        "claim": "Silent prospective / shadow-mode hospital deployment metrics",
        "status": "under_evaluation",
        "evidence": ["Durable store + security boundaries in place; no live site yet"],
    },
    {
        "id": "LLM-STEWARD",
        "claim": "LLM feedback classification improves alert stewardship",
        "status": "under_evaluation",
        "evidence": ["Roadmap CURIE-024 / llm-workflows.md"],
    },
    {
        "id": "DX-SEPSIS",
        "claim": "Diagnoses sepsis (or AKI / respiratory failure) for a patient",
        "status": "not_claimed",
        "evidence": ["Signals are surveillance scores/phenotypes — not diagnoses"],
    },
    {
        "id": "OUTCOME-MORT",
        "claim": "Improves mortality, organ failure, or time-to-antibiotics",
        "status": "not_claimed",
        "evidence": ["No outcome endpoints estimated in manuscript package"],
    },
    {
        "id": "CLIN-VALID",
        "claim": "Clinically validated for patient care",
        "status": "not_claimed",
        "evidence": ["Prototype posture; Stage B–E incomplete"],
    },
    {
        "id": "REG-CLEAR",
        "claim": "FDA cleared / SaMD authorized",
        "status": "not_claimed",
        "evidence": ["No regulatory submission"],
    },
    {
        "id": "SUPERIOR-NEWS",
        "claim": "Superior to NEWS/qSOFA/vendor CDS across sites",
        "status": "not_claimed",
        "evidence": ["Not evaluated"],
    },
]


def claims_matrix(*, schema_version: str = "1.0.0") -> dict[str, Any]:
    by_status: dict[str, list[str]] = {
        "demonstrated": [],
        "under_evaluation": [],
        "not_claimed": [],
    }
    for row in CLAIMS:
        by_status[row["status"]].append(row["id"])
    return {
        "schema_version": schema_version,
        "curie_ticket": "CURIE-021",
        "disclaimer": (
            "Prototype claims matrix for investor/demo communication. "
            "Not a regulatory claims matrix. Do not imply clinical validation."
        ),
        "claims": CLAIMS,
        "by_status": by_status,
    }


def write_claims_matrix(path: Path | None = None) -> Path:
    out = path or CLAIMS_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(claims_matrix(), indent=2) + "\n")
    return out


def load_claims_matrix(path: Path | None = None) -> dict[str, Any]:
    p = path or CLAIMS_PATH
    if p.is_file():
        return json.loads(p.read_text())
    return claims_matrix()
