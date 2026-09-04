"""Feature flags for Phase 2 LLM surfaces. Deterministic path never depends on these."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def running_in_docker() -> bool:
    """True inside a container (Compose sets CURIE_IN_DOCKER=1 as a fallback)."""
    return Path("/.dockerenv").exists() or os.environ.get("CURIE_IN_DOCKER") == "1"


def rewrite_grp_base_url(url: str, *, in_docker: bool | None = None) -> str:
    """Host loopback inside Docker is the container, not LM Studio on the Mac.

    Leave non-loopback URLs (cloud OpenAI, LAN vLLM) unchanged.
    """
    if not (running_in_docker() if in_docker is None else in_docker):
        return url
    return url.replace("://127.0.0.1", "://host.docker.internal").replace(
        "://localhost", "://host.docker.internal"
    )


class CurieSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CURIE_", env_file=".env", extra="ignore")

    # Extraction adapter (notes → FHIR). Off by default.
    enable_extraction: bool = False
    extraction_backend: str = "deterministic"  # deterministic | openai_compat (future)

    # Guarded Reasoning Pipeline (post-alert narrative only). Off by default.
    enable_grp: bool = False
    grp_backend: str = "deterministic"  # deterministic | openai_compat
    grp_model_name: str = "curie-grp-stub-v1"
    # OpenAI-compatible endpoint (LM Studio, vLLM, etc.)
    grp_base_url: str = "http://127.0.0.1:1234/v1"
    grp_api_key: str = "lm-studio"
    grp_timeout_s: float = 120.0
    grp_max_tokens: int = 512
    grp_temperature: float = 0.0

    # Hard policy
    grp_fail_closed: bool = True  # ungrounded claim → quarantine, never attach narrative

    @field_validator("grp_base_url")
    @classmethod
    def _docker_loopback(cls, value: str) -> str:
        return rewrite_grp_base_url(value)


settings = CurieSettings()
