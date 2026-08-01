from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from agentkit.identity import OidcJwtVerifier


def test_oidc_issuer_with_trailing_slash_is_compared_exactly():
    issuer = "https://issuer.example.com/"
    client = "agentkit-client"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    compact = jwt.encode(
        {
            "sub": "alice",
            "iss": issuer,
            "aud": client,
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
    )
    verifier = OidcJwtVerifier(
        discovery_url=issuer,
        expected_issuer=issuer,
        allowed_clients=(client,),
        discovery_document={
            "issuer": issuer,
            "jwks_uri": "https://issuer.example.com/jwks",
        },
        signing_key_resolver=lambda _: private_key.public_key(),
    )
    assert verifier.verify(compact).issuer == issuer
