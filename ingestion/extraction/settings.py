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
    grp_backend: str = "deterministic"  # deterministic | openai_compat (future)
    grp_model_name: str = "curie-grp-stub-v1"

    # Hard policy
    grp_fail_closed: bool = True  # ungrounded claim → quarantine, never attach narrative


settings = CurieSettings()
