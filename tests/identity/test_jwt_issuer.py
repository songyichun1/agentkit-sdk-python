from __future__ import annotations

import time

import jwt

from agentkit.identity import OidcJwtVerifier


def test_oidc_issuer_with_trailing_slash_is_compared_exactly():
    issuer = "https://issuer.example.com/"
    client = "agentkit-client"
    secret = "test-signing-secret-0123456789abcdef"
    now = int(time.time())
    compact = jwt.encode(
        {
            "sub": "alice",
            "iss": issuer,
            "aud": client,
            "iat": now,
            "exp": now + 300,
        },
        secret,
        algorithm="HS256",
    )
    verifier = OidcJwtVerifier(
        discovery_url=issuer,
        allowed_clients=(client,),
        allowed_algorithms=("HS256",),
        discovery_document={
            "issuer": issuer,
            "jwks_uri": "https://issuer.example.com/jwks",
        },
        signing_key_resolver=lambda _: secret,
    )
    assert verifier.verify(compact).issuer == issuer
