from __future__ import annotations

import agentkit_identity.jwt as identity_jwt
import jwt
from agentkit_identity.jwt import _PinnedPyJWKClient
from cryptography.hazmat.primitives.asymmetric import rsa


def _jwk(public_key, *, kid: str) -> dict[str, object]:
    value = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    value.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return value


def test_same_kid_rotation_takes_effect_when_the_bounded_jwks_cache_expires(
    monkeypatch,
):
    first_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    second_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    active_document = {"keys": [_jwk(first_key.public_key(), kid="shared-kid")]}

    def read_document(*args, **kwargs):
        return active_document

    monkeypatch.setattr(identity_jwt, "_read_json_document", read_document)
    client = _PinnedPyJWKClient(
        "https://issuer.example.com/jwks",
        cache_keys=False,
        lifespan=1,
    )

    first_token = jwt.encode(
        {"sub": "alice"},
        first_key,
        algorithm="RS256",
        headers={"kid": "shared-kid"},
    )
    resolved_first = client.get_signing_key_from_jwt(first_token).key
    assert resolved_first.public_numbers() == first_key.public_key().public_numbers()

    active_document = {"keys": [_jwk(second_key.public_key(), kid="shared-kid")]}
    cached = client.jwk_set_cache.jwk_set_with_timestamp
    assert cached is not None
    cached.timestamp -= 2

    second_token = jwt.encode(
        {"sub": "alice"},
        second_key,
        algorithm="RS256",
        headers={"kid": "shared-kid"},
    )
    resolved_second = client.get_signing_key_from_jwt(second_token).key
    assert resolved_second.public_numbers() == second_key.public_key().public_numbers()
