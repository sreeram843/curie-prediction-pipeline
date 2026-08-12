"""CURIE-038 JWT / JWKS verification tests."""

from __future__ import annotations

import base64
import json
import time

import pytest

from action.api.app.jwt_verify import (
    JwksCache,
    JwtVerificationError,
    mint_hs256_for_tests,
    role_from_claims,
    verify_jwt,
)


def _jwks_inline(secret: bytes, kid: str = "k1") -> JwksCache:
    k = base64.urlsafe_b64encode(secret).rstrip(b"=").decode("ascii")
    doc = {"keys": [{"kty": "oct", "kid": kid, "alg": "HS256", "k": k}]}
    return JwksCache(json.dumps(doc))


def test_accepts_valid_hs256() -> None:
    secret = b"super-secret-key-for-tests!!"
    jwks = _jwks_inline(secret)
    now = int(time.time())
    token = mint_hs256_for_tests(
        {
            "sub": "user-1",
            "iss": "https://issuer.example",
            "aud": "curie-api",
            "exp": now + 60,
            "roles": ["clinician"],
            "tenant_id": "hospital-a",
        },
        secret=secret,
        kid="k1",
    )
    claims = verify_jwt(
        token,
        jwks=jwks,
        issuer="https://issuer.example",
        audience="curie-api",
    )
    assert claims.sub == "user-1"
    assert role_from_claims(claims) == "clinician"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda c: {**c, "exp": int(time.time()) - 10}, "expired"),
        (lambda c: {**c, "iss": "https://other"}, "wrong issuer"),
        (lambda c: {**c, "aud": "other-aud"}, "wrong audience"),
        (lambda c: {**c, "nbf": int(time.time()) + 100}, "not yet valid"),
    ],
)
def test_rejects_bad_claims(mutate, match) -> None:
    secret = b"super-secret-key-for-tests!!"
    jwks = _jwks_inline(secret)
    now = int(time.time())
    claims = {
        "sub": "user-1",
        "iss": "https://issuer.example",
        "aud": "curie-api",
        "exp": now + 60,
    }
    token = mint_hs256_for_tests(mutate(claims), secret=secret, kid="k1")
    with pytest.raises(JwtVerificationError, match=match):
        verify_jwt(
            token,
            jwks=jwks,
            issuer="https://issuer.example",
            audience="curie-api",
        )


def test_unknown_kid_after_rotation_fails() -> None:
    secret = b"super-secret-key-for-tests!!"
    jwks = _jwks_inline(secret, kid="old")
    token = mint_hs256_for_tests(
        {
            "sub": "user-1",
            "iss": "https://issuer.example",
            "aud": "curie-api",
            "exp": int(time.time()) + 60,
        },
        secret=secret,
        kid="rotated",
    )
    with pytest.raises(JwtVerificationError, match="unknown kid"):
        verify_jwt(
            token,
            jwks=jwks,
            issuer="https://issuer.example",
            audience="curie-api",
        )


def test_signature_tamper_rejected() -> None:
    secret = b"super-secret-key-for-tests!!"
    jwks = _jwks_inline(secret)
    token = mint_hs256_for_tests(
        {
            "sub": "user-1",
            "iss": "https://issuer.example",
            "aud": "curie-api",
            "exp": int(time.time()) + 60,
        },
        secret=secret,
        kid="k1",
    )
    bad = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(JwtVerificationError, match="signature"):
        verify_jwt(
            bad,
            jwks=jwks,
            issuer="https://issuer.example",
            audience="curie-api",
        )
