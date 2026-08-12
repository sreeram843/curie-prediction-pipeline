"""Feature flags for Phase 2 LLM surfaces. Deterministic path never depends on these."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = CurieSettings()
