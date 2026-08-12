"""Security settings: auth, CORS, tenant boundaries (CURIE-018)."""

from __future__ import annotations

import hmac
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CURIE_", env_file=".env", extra="ignore")

    env: str = "development"  # development | staging | production
    # Comma-separated origins. Empty in production → no browser CORS (fail closed).
    cors_origins: str = ""
    # Comma-separated API keys. Required when require_auth is true.
    api_keys: str = ""
    # Force auth even in development when true.
    require_auth: bool | None = None
    # Optional OIDC / JWT (validated when issuer set and token is Bearer JWT-shaped).
    oidc_issuer: str = ""
    oidc_audience: str = ""
    # JWKS URI or inline JWKS JSON for signature verification (CURIE-038).
    oidc_jwks_uri: str = ""
    # TLS is expected at the reverse proxy; API records the posture.
    tls_terminated: bool = False
    # Tenant / site boundary tags (propagated into ops + logs).
    tenant_id: str = "local"
    site_id: str = "dev"
    # Bind hint for operators (make api uses 127.0.0.1).
    bind_host: str = "127.0.0.1"

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() in {"production", "prod"}

    @property
    def auth_required(self) -> bool:
        if self.require_auth is not None:
            return bool(self.require_auth)
        return self.is_production

    def cors_origin_list(self) -> list[str]:
        raw = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.is_production:
            # Never allow wildcard in production.
            return [o for o in raw if o != "*"]
        if not raw:
            # Local demo: allow same-origin style localhost only (not "*").
            return [
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://127.0.0.1:8001",
                "http://localhost:8001",
                "http://127.0.0.1:8002",
                "http://localhost:8002",
                "http://127.0.0.1:8003",
                "http://localhost:8003",
            ]
        return [o for o in raw if o != "*"] if self.is_production else raw

    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    def validate_production_posture(self) -> list[str]:
        """Return blocking misconfiguration reasons for production boot."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if "*" in self.cors_origins.split(","):
            problems.append("CURIE_CORS_ORIGINS must not contain '*' in production")
        if self.auth_required and not self.api_key_set() and not self.oidc_issuer:
            problems.append(
                "Production requires CURIE_API_KEYS and/or CURIE_OIDC_ISSUER when auth is required"
            )
        if self.bind_host in {"0.0.0.0", "::"} and not self.tls_terminated:
            problems.append(
                "Binding 0.0.0.0 without CURIE_TLS_TERMINATED=true is refused in production"
            )
        return problems


@lru_cache(maxsize=1)
def get_security_settings() -> SecuritySettings:
    return SecuritySettings()


def reset_security_settings() -> None:
    get_security_settings.cache_clear()


def constant_time_key_match(provided: str, allowed: set[str]) -> bool:
    if not provided or not allowed:
        return False
    return any(hmac.compare_digest(provided, key) for key in allowed)


def role_for_principal(principal: str) -> str:
    """Minimal RBAC: ops keys vs clinician keys by prefix convention."""
    if principal.startswith("ops:") or principal.endswith(":ops"):
        return "ops"
    if principal.startswith("admin:"):
        return "admin"
    return "clinician"


PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)
