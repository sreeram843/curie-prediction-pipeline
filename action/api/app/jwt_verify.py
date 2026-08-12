"""Verified JWT / OIDC identity (CURIE-038).

Production paths verify signatures via JWKS (HS256/RS256). The insecure
payload-only decode remains available only when ``CURIE_OIDC_INSECURE_DEV`` is
explicitly enabled — never the production default.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class JwtVerificationError(Exception):
    """Token rejected — fail closed."""


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass
class VerifiedClaims:
    sub: str
    iss: str
    aud: str | list[str]
    exp: int
    nbf: int | None
    roles: list[str]
    tenant_id: str | None
    raw: dict[str, Any]


class JwksCache:
    """Cached JWKS with simple TTL. Key rotation: unknown kid is rejected."""

    def __init__(self, jwks_uri: str, *, ttl_seconds: int = 300) -> None:
        self.jwks_uri = jwks_uri
        self.ttl_seconds = ttl_seconds
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float = 0.0

    def _refresh(self, force: bool = False) -> None:
        now = time.time()
        if not force and self._keys and (now - self._fetched_at) < self.ttl_seconds:
            return
        # Support data: URIs and inline JSON for tests / air-gapped demos.
        if self.jwks_uri.startswith("{"):
            doc = json.loads(self.jwks_uri)
        elif self.jwks_uri.startswith("data:"):
            _, _, payload = self.jwks_uri.partition(",")
            doc = json.loads(base64.b64decode(payload) if ";base64" in self.jwks_uri else payload)
        else:
            try:
                with urllib.request.urlopen(self.jwks_uri, timeout=5) as resp:  # noqa: S310
                    doc = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise JwtVerificationError(f"JWKS fetch failed: {exc}") from exc
        keys = {}
        for key in doc.get("keys") or []:
            kid = str(key.get("kid") or "")
            if kid:
                keys[kid] = key
        if not keys:
            raise JwtVerificationError("JWKS contained no keys")
        self._keys = keys
        self._fetched_at = now

    def get_key(self, kid: str) -> dict[str, Any]:
        self._refresh()
        if kid not in self._keys:
            # One forced refresh for rotation, then fail closed.
            self._refresh(force=True)
        if kid not in self._keys:
            raise JwtVerificationError(f"unknown kid {kid!r}")
        return self._keys[kid]


def _verify_hs256(signing_input: bytes, signature: bytes, key: dict[str, Any]) -> None:
    k = key.get("k")
    if not k:
        raise JwtVerificationError("HS256 key missing 'k'")
    secret = _b64url_decode(str(k))
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        raise JwtVerificationError("signature mismatch")


def _verify_rs256(signing_input: bytes, signature: bytes, key: dict[str, Any]) -> None:
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
    except ImportError as exc:  # pragma: no cover
        raise JwtVerificationError(
            "RS256 verification requires the 'cryptography' package"
        ) from exc

    def _int(seg: str) -> int:
        return int.from_bytes(_b64url_decode(seg), "big")

    n = _int(str(key["n"]))
    e = _int(str(key["e"]))
    pub = RSAPublicNumbers(e, n).public_key(default_backend())
    try:
        pub.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        raise JwtVerificationError("signature mismatch") from exc


def verify_jwt(
    token: str,
    *,
    jwks: JwksCache,
    issuer: str,
    audience: str,
    now: float | None = None,
) -> VerifiedClaims:
    parts = token.split(".")
    if len(parts) != 3:
        raise JwtVerificationError("malformed JWT")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except Exception as exc:
        raise JwtVerificationError("malformed JWT encoding") from exc

    alg = str(header.get("alg") or "")
    if alg not in {"HS256", "RS256"}:
        raise JwtVerificationError(f"unsupported alg {alg!r}")
    kid = str(header.get("kid") or "")
    if not kid:
        raise JwtVerificationError("missing kid")
    key = jwks.get_key(kid)
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    if alg == "HS256":
        _verify_hs256(signing_input, signature, key)
    else:
        _verify_rs256(signing_input, signature, key)

    ts = now if now is not None else time.time()
    if payload.get("iss") != issuer:
        raise JwtVerificationError("wrong issuer")
    aud = payload.get("aud")
    if aud != audience and not (isinstance(aud, list) and audience in aud):
        raise JwtVerificationError("wrong audience")
    exp = payload.get("exp")
    if exp is None or float(exp) < ts:
        raise JwtVerificationError("expired")
    nbf = payload.get("nbf")
    if nbf is not None and float(nbf) > ts:
        raise JwtVerificationError("not yet valid")
    sub = str(payload.get("sub") or "")
    if not sub:
        raise JwtVerificationError("missing sub")
    roles = payload.get("roles") or payload.get("groups") or []
    if isinstance(roles, str):
        roles = [roles]
    return VerifiedClaims(
        sub=sub,
        iss=str(payload.get("iss")),
        aud=aud,
        exp=int(exp),
        nbf=int(nbf) if nbf is not None else None,
        roles=[str(r) for r in roles],
        tenant_id=(str(payload["tenant_id"]) if payload.get("tenant_id") else None),
        raw=payload,
    )


def mint_hs256_for_tests(
    claims: dict[str, Any],
    *,
    secret: bytes,
    kid: str = "test-hs",
) -> str:
    """Test helper — not for production minting."""
    header = _b64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT", "kid": kid}, separators=(",", ":")).encode()
    )
    body = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    sig = _b64url_encode(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def role_from_claims(claims: VerifiedClaims) -> str:
    roles = {r.lower() for r in claims.roles}
    if "admin" in roles or "ops" in roles:
        return "ops" if "ops" in roles and "admin" not in roles else "admin"
    if "reviewer" in roles:
        return "reviewer"
    return "clinician"
