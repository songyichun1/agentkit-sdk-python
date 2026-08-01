from __future__ import annotations

import time
from dataclasses import replace

import jwt
import pytest

from agentkit.identity import (
    IdentityRuntimeConfig,
    ProtectedTarget,
    RuntimeIdentity,
    TokenExchangeError,
    VerifiedUserIdentity,
    WorkloadBindingError,
    WorkloadJwtVerifier,
)
from agentkit.identity.context import _bind_identity, _reset_identity


class _Verifier:
    def verify(self, compact):
        now = int(time.time())
        return VerifiedUserIdentity(
            subject="alice",
            issuer="https://issuer.example.com",
            audiences=("client",),
            client_id="client",
            expires_at=now + 300,
            issued_at=now,
            claims={"sub": "alice"},
        )


class _Exchange:
    def __init__(self, *, actor="r-1"):
        self.actor = actor
        self.calls = []

    def exchange_for_jwt(self, **kwargs):
        self.calls.append(kwargs)
        now = int(time.time())
        compact = jwt.encode(
            {
                "sub": "alice",
                "iss": "https://workload.example.com/pool-1",
                "act": {"sub": self.actor},
                "aud": kwargs["audience"],
                "iat": now,
                "exp": now + 300,
            },
            "tip-signing-secret-0123456789abcdef",
            algorithm="HS256",
        )
        return compact, now + 300


def _config():
    return IdentityRuntimeConfig(
        runtime_id="r-1",
        discovery_url="https://issuer.example.com",
        allowed_clients=("client",),
        workload_discovery_url="https://workload.example.com/pool-1",
        targets={
            "bpm": ProtectedTarget(
                alias="bpm",
                audience="trn:customer:bpm-api",
                base_url="https://gateway.example.com/bpm",
            )
        },
    )


def _workload_verifier():
    return WorkloadJwtVerifier(
        discovery_url="https://workload.example.com/pool-1",
        allowed_algorithms=("HS256",),
        discovery_document={
            "issuer": "https://workload.example.com/pool-1",
            "jwks_uri": "https://workload.example.com/pool-1/.well-known/jwks",
        },
        signing_key_resolver=lambda _: "tip-signing-secret-0123456789abcdef",
    )


def test_runtime_id_is_the_fixed_workload_id():
    config = _config()
    assert config.workload_id == config.runtime_id == "r-1"
    with pytest.raises(WorkloadBindingError):
        IdentityRuntimeConfig(
            runtime_id="r-1",
            workload_id="other",
            discovery_url="https://issuer.example.com",
            allowed_clients=("client",),
            targets=config.targets,
        )


def test_protected_targets_require_an_explicit_trusted_exchange():
    with pytest.raises(WorkloadBindingError, match="explicit trusted token exchange"):
        RuntimeIdentity(
            _config(),
            verifier=_Verifier(),
            workload_verifier=_workload_verifier(),
        )


def test_for_jwt_is_target_bound_and_cached():
    exchange = _Exchange()
    runtime = RuntimeIdentity(
        _config(),
        verifier=_Verifier(),
        workload_verifier=_workload_verifier(),
        exchange=exchange,
    )
    authenticated = runtime._authenticate("Bearer user.jwt.value")
    marker = _bind_identity(
        authenticated.context,
        owner=runtime,
        user_token=authenticated.user_token,
    )
    try:
        first = runtime._token_for("bpm")
        second = runtime._token_for("bpm")
    finally:
        _reset_identity(marker)
    assert first is second
    assert len(exchange.calls) == 1
    assert exchange.calls[0]["workload_id"] == "r-1"
    assert exchange.calls[0]["audience"] == "trn:customer:bpm-api"
    assert "user.jwt.value" not in repr(authenticated.context)
    assert "user.jwt.value" not in repr(first)


def test_delegation_receipt_contains_verified_metadata_and_no_token():
    exchange = _Exchange()
    runtime = RuntimeIdentity(
        _config(),
        verifier=_Verifier(),
        workload_verifier=_workload_verifier(),
        exchange=exchange,
    )
    authenticated = runtime._authenticate("Bearer user.jwt.value")
    marker = _bind_identity(
        authenticated.context,
        owner=runtime,
        user_token=authenticated.user_token,
    )
    try:
        receipt = runtime.delegation_receipt("bpm")
    finally:
        _reset_identity(marker)

    assert receipt.target_alias == "bpm"
    assert receipt.subject == "alice"
    assert receipt.actor == "r-1"
    assert receipt.audience == "trn:customer:bpm-api"
    assert receipt.expires_at > int(time.time())
    assert receipt.invocation_id
    assert "user.jwt.value" not in repr(receipt)


def test_rejects_tip_for_another_actor():
    runtime = RuntimeIdentity(
        _config(),
        verifier=_Verifier(),
        workload_verifier=_workload_verifier(),
        exchange=_Exchange(actor="r-other"),
    )
    authenticated = runtime._authenticate("Bearer user.jwt.value")
    marker = _bind_identity(
        authenticated.context,
        owner=runtime,
        user_token=authenticated.user_token,
    )
    try:
        with pytest.raises(TokenExchangeError):
            runtime._token_for("bpm")
    finally:
        _reset_identity(marker)


def test_cache_is_bound_to_subject_token_and_capacity_is_bounded():
    exchange = _Exchange()
    runtime = RuntimeIdentity(
        replace(_config(), max_cached_tokens=1),
        verifier=_Verifier(),
        workload_verifier=_workload_verifier(),
        exchange=exchange,
    )
    for compact in ("user.jwt.first", "user.jwt.second"):
        authenticated = runtime._authenticate(f"Bearer {compact}")
        marker = _bind_identity(
            authenticated.context,
            owner=runtime,
            user_token=authenticated.user_token,
        )
        try:
            runtime._token_for("bpm")
        finally:
            _reset_identity(marker)

    assert len(exchange.calls) == 2
    assert len(runtime._cache) == 1
