from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from agentkit_identity import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
    OidcJwtVerifier,
    WorkloadJwtVerifier,
)

ISSUER = "https://issuer.example.com"
CLIENT = "agentkit-client"
SECRET = "test-signing-secret-0123456789abcdef"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()


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
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256")


def _verifier(*, allowed_clients=(CLIENT,)):
    return OidcJwtVerifier(
        discovery_url=ISSUER,
        expected_issuer=ISSUER,
        allowed_clients=allowed_clients,
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://issuer.example.com/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )


def _assert_secret_absent_from_package_traceback(exc, secret):
    traceback = exc.__traceback__
    matched = 0
    while traceback is not None:
        if "/agentkit_identity/" in traceback.tb_frame.f_code.co_filename:
            matched += 1
            assert secret not in repr(traceback.tb_frame.f_locals)
        traceback = traceback.tb_next
    assert matched > 0


def test_verifies_and_redacts_id_token():
    compact = _token()
    verified = _verifier().verify(compact)
    assert verified.subject == "alice"
    assert compact not in repr(verified)


def test_oidc_verifier_failure_traceback_does_not_retain_id_token():
    secret = "secret-id-token.payload.signature"
    with pytest.raises(IdentityAuthenticationError) as caught:
        _verifier().verify(secret)
    assert secret not in str(caught.value)
    _assert_secret_absent_from_package_traceback(caught.value, secret)


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


def test_authorized_party_must_be_an_allowed_audience():
    with pytest.raises(IdentityAuthenticationError):
        _verifier(allowed_clients=(CLIENT, "other-client")).verify(
            _token(aud=[CLIENT, "resource"], azp="other-client")
        )


def test_nonce_is_verified_when_requested():
    with pytest.raises(IdentityAuthenticationError):
        _verifier().verify(_token(nonce="n1"), nonce="n2")


def test_runtime_verifier_rejects_insecure_loopback_by_default():
    with pytest.raises(ValueError, match="HTTPS"):
        OidcJwtVerifier(
            discovery_url="http://127.0.0.1:8080",
            expected_issuer="http://127.0.0.1:8080",
            allowed_clients=(CLIENT,),
        )


def test_discovery_declared_cross_origin_jwks_requires_an_allowlist():
    verifier = OidcJwtVerifier(
        discovery_url=ISSUER,
        expected_issuer=ISSUER,
        allowed_clients=(CLIENT,),
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://keys.example.net/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )
    with pytest.raises(IdentityUnavailableError):
        verifier.verify(_token())

    verifier = OidcJwtVerifier(
        discovery_url=ISSUER,
        expected_issuer=ISSUER,
        allowed_clients=(CLIENT,),
        allowed_jwks_origins=("https://keys.example.net",),
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://keys.example.net/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )
    assert verifier.verify(_token()).subject == "alice"


def test_explicit_jwks_origin_allowlist_is_strict():
    verifier = OidcJwtVerifier(
        discovery_url=ISSUER,
        expected_issuer=ISSUER,
        allowed_clients=(CLIENT,),
        allowed_jwks_origins=("https://approved.example.net",),
        discovery_document={
            "issuer": ISSUER,
            "jwks_uri": "https://keys.example.net/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
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
        PRIVATE_KEY,
        algorithm="RS256",
    )
    verifier = WorkloadJwtVerifier(
        discovery_url=issuer,
        expected_issuer=issuer,
        discovery_document={
            "issuer": issuer,
            "jwks_uri": f"{issuer}/.well-known/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )
    claims = verifier.verify(compact, audience=audience)
    assert claims["act"]["sub"] == "runtime-1"
    with pytest.raises(IdentityAuthenticationError):
        verifier.verify(compact, audience="trn:customer:other-api")


def test_workload_verifier_failure_traceback_does_not_retain_tip():
    issuer = "https://workload.example.com/pool-1"
    audience = "trn:customer:expense-api"
    secret = "secret-workload-tip.payload.signature"
    verifier = WorkloadJwtVerifier(
        discovery_url=issuer,
        expected_issuer=issuer,
        discovery_document={
            "issuer": issuer,
            "jwks_uri": f"{issuer}/.well-known/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )
    with pytest.raises(IdentityAuthenticationError) as caught:
        verifier.verify(secret, audience=audience)
    assert secret not in str(caught.value)
    _assert_secret_absent_from_package_traceback(caught.value, secret)


def test_workload_token_verifier_normalizes_integral_numeric_dates():
    issuer = "https://workload.example.com/pool-1"
    audience = "trn:customer:expense-api"
    now = int(time.time())
    verifier = WorkloadJwtVerifier(
        discovery_url=issuer,
        expected_issuer=issuer,
        discovery_document={
            "issuer": issuer,
            "jwks_uri": f"{issuer}/.well-known/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )
    compact = jwt.encode(
        {
            "sub": "alice",
            "iss": issuer,
            "aud": audience,
            "iat": float(now),
            "exp": float(now + 300),
            "act": {"sub": "runtime-1"},
        },
        PRIVATE_KEY,
        algorithm="RS256",
    )

    claims = verifier.verify(compact, audience=audience)

    assert claims["iat"] == now
    assert claims["exp"] == now + 300
    assert isinstance(claims["iat"], int)
    assert isinstance(claims["exp"], int)


@pytest.mark.parametrize("issued_at", [1.5, float("nan"), float("inf"), True])
def test_workload_token_verifier_rejects_non_integral_numeric_dates(issued_at):
    issuer = "https://workload.example.com/pool-1"
    audience = "trn:customer:expense-api"
    now = int(time.time())
    compact = jwt.encode(
        {
            "sub": "alice",
            "iss": issuer,
            "aud": audience,
            "iat": issued_at,
            "exp": now + 300,
            "act": {"sub": "runtime-1"},
        },
        PRIVATE_KEY,
        algorithm="RS256",
    )
    verifier = WorkloadJwtVerifier(
        discovery_url=issuer,
        expected_issuer=issuer,
        discovery_document={
            "issuer": issuer,
            "jwks_uri": f"{issuer}/.well-known/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )

    with pytest.raises(IdentityAuthenticationError):
        verifier.verify(compact, audience=audience)


def test_discovery_issuer_must_match_the_configured_trust_anchor():
    verifier = OidcJwtVerifier(
        discovery_url=ISSUER,
        expected_issuer=ISSUER,
        allowed_clients=(CLIENT,),
        discovery_document={
            "issuer": "https://attacker.example.com",
            "jwks_uri": "https://issuer.example.com/jwks",
        },
        signing_key_resolver=lambda _: PUBLIC_KEY,
    )
    with pytest.raises(IdentityUnavailableError):
        verifier.verify(_token())


def test_public_verifiers_reject_symmetric_algorithms():
    with pytest.raises(ValueError, match="asymmetric"):
        OidcJwtVerifier(
            discovery_url=ISSUER,
            expected_issuer=ISSUER,
            allowed_clients=(CLIENT,),
            allowed_algorithms=("HS256",),
        )
    with pytest.raises(ValueError, match="asymmetric"):
        WorkloadJwtVerifier(
            discovery_url=ISSUER,
            expected_issuer=ISSUER,
            allowed_algorithms=("HS256",),
        )
