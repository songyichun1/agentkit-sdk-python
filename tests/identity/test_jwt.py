from __future__ import annotations

import time

import jwt
import pytest

from agentkit.identity import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
    OidcJwtVerifier,
    WorkloadJwtVerifier,
)

ISSUER = "https://issuer.example.com"
CLIENT = "agentkit-client"
SECRET = "test-signing-secret-0123456789abcdef"


def _token(**overrides):
    now = int(time.time())
    claims = {
        "sub": "alice",
        "iss": ISSUER,
        "aud": CLIENT,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _verifier():
    return OidcJwtVerifier(
        discovery_url=ISSUER,
        allowed_clients=(CLIENT,),
        allowed_algorithms=("HS256",),
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://issuer.example.com/jwks",
        },
        signing_key_resolver=lambda _: SECRET,
    )


def test_verifies_and_redacts_id_token():
    compact = _token()
    verified = _verifier().verify(compact)
    assert verified.subject == "alice"
    assert compact not in repr(verified)


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://other.example.com"},
        {"aud": "other-client"},
        {"sub": ""},
        {"exp": 1},
    ],
)
def test_rejects_invalid_identity_claims(claims):
    with pytest.raises(IdentityAuthenticationError):
        _verifier().verify(_token(**claims))


def test_multi_audience_requires_allowed_azp():
    with pytest.raises(IdentityAuthenticationError):
        _verifier().verify(_token(aud=[CLIENT, "resource"]))
    verified = _verifier().verify(_token(aud=[CLIENT, "resource"], azp=CLIENT))
    assert verified.client_id == CLIENT


def test_nonce_is_verified_when_requested():
    with pytest.raises(IdentityAuthenticationError):
        _verifier().verify(_token(nonce="n1"), nonce="n2")


def test_runtime_verifier_rejects_insecure_loopback_by_default():
    with pytest.raises(ValueError, match="HTTPS"):
        OidcJwtVerifier(
            discovery_url="http://127.0.0.1:8080",
            allowed_clients=(CLIENT,),
        )


def test_discovery_declared_cross_origin_jwks_is_supported():
    verifier = OidcJwtVerifier(
        discovery_url=ISSUER,
        allowed_clients=(CLIENT,),
        allowed_algorithms=("HS256",),
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://keys.example.net/jwks",
        },
        signing_key_resolver=lambda _: SECRET,
    )
    assert verifier.verify(_token()).subject == "alice"


def test_explicit_jwks_origin_allowlist_is_strict():
    verifier = OidcJwtVerifier(
        discovery_url=ISSUER,
        allowed_clients=(CLIENT,),
        allowed_algorithms=("HS256",),
        allowed_jwks_origins=("https://approved.example.net",),
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://keys.example.net/jwks",
        },
        signing_key_resolver=lambda _: SECRET,
    )
    with pytest.raises(IdentityUnavailableError):
        verifier.verify(_token())


def test_workload_token_verifier_checks_signature_issuer_and_audience():
    issuer = "https://workload.example.com/pool-1"
    audience = "trn:customer:expense-api"
    now = int(time.time())
    compact = jwt.encode(
        {
            "sub": "alice",
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + 300,
            "act": {"sub": "runtime-1"},
        },
        SECRET,
        algorithm="HS256",
    )
    verifier = WorkloadJwtVerifier(
        discovery_url=issuer,
        allowed_algorithms=("HS256",),
        discovery_document={
            "issuer": issuer,
            "jwks_uri": f"{issuer}/.well-known/jwks",
        },
        signing_key_resolver=lambda _: SECRET,
    )
    claims = verifier.verify(compact, audience=audience)
    assert claims["act"]["sub"] == "runtime-1"
    with pytest.raises(IdentityAuthenticationError):
        verifier.verify(compact, audience="trn:customer:other-api")
