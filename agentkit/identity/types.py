# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Public, immutable models for AgentKit Runtime identity."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol
from urllib.parse import urlsplit

from agentkit.identity.errors import WorkloadBindingError

_REGION = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_ASYMMETRIC_JWT_ALGORITHMS = frozenset(
    {
        "EdDSA",
        "ES256",
        "ES384",
        "ES512",
        "PS256",
        "PS384",
        "PS512",
        "RS256",
        "RS384",
        "RS512",
    }
)


@dataclass(frozen=True, repr=False)
class VerifiedUserIdentity:
    """Safe metadata derived from a cryptographically verified OIDC ID Token."""

    subject: str
    issuer: str
    audiences: tuple[str, ...]
    client_id: str
    expires_at: int
    issued_at: int
    claims: Mapping[str, Any] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "claims", MappingProxyType(dict(self.claims)))

    def __repr__(self) -> str:
        return (
            "VerifiedUserIdentity("
            f"subject={self.subject!r}, issuer={self.issuer!r}, "
            f"audiences={self.audiences!r}, client_id={self.client_id!r}, "
            f"expires_at={self.expires_at!r})"
        )


@dataclass(frozen=True)
class ProtectedTarget:
    """A deployment-controlled mapping from a logical alias to one audience."""

    alias: str
    audience: str
    base_url: str | None = None

    def __post_init__(self) -> None:
        if not self.alias or not self.audience:
            raise ValueError("target alias and audience are required")
        if self.base_url is None:
            return
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("protected target base_url must be an absolute HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "protected target base_url cannot contain credentials, query, or fragment"
            )


@dataclass(frozen=True)
class DelegationReceipt:
    """Token-free evidence for one SDK-verified OBO delegation."""

    target_alias: str
    subject: str
    actor: str
    audience: str
    expires_at: int
    invocation_id: str


@dataclass(frozen=True)
class IdentityRuntimeConfig:
    """Trusted Runtime configuration supplied by AgentKit deployment code.

    AgentKit currently uses the Runtime ID as the Workload Identity name.  The
    equality is checked at construction time and cannot be changed per request.
    A future APIG/control-plane registry can construct the same immutable type.
    """

    runtime_id: str
    discovery_url: str
    expected_user_issuer: str
    allowed_clients: tuple[str, ...]
    targets: Mapping[str, ProtectedTarget]
    workload_discovery_url: str | None = None
    expected_workload_issuer: str | None = None
    workload_pool: str = "default"
    workload_id: str | None = None
    region: str = "cn-beijing"
    token_duration_seconds: int = 300
    allowed_algorithms: tuple[str, ...] = ("RS256",)
    workload_allowed_algorithms: tuple[str, ...] = ("RS256",)
    allowed_jwks_origins: tuple[str, ...] = ()
    workload_allowed_jwks_origins: tuple[str, ...] = ()
    clock_skew_seconds: int = 30
    jwks_cache_seconds: int = 300
    workload_jwks_cache_seconds: int = 300
    max_cached_tokens: int = 1024

    def __post_init__(self) -> None:
        workload_id = self.workload_id or self.runtime_id
        if not self.runtime_id or workload_id != self.runtime_id:
            raise WorkloadBindingError(
                "AgentKit Runtime ID must equal its configured Workload Identity"
            )
        if not self.workload_pool:
            raise WorkloadBindingError("Workload pool is required")
        if _REGION.fullmatch(self.region) is None:
            raise WorkloadBindingError("Agent Identity region is invalid")
        if not self.allowed_clients:
            raise ValueError("at least one allowed OIDC client is required")
        if not self.expected_user_issuer:
            raise ValueError("the expected user token issuer is required")
        if not 60 <= self.token_duration_seconds <= 3600:
            raise ValueError("token duration must be between 60 and 3600 seconds")
        if not self.allowed_algorithms:
            raise ValueError("at least one JWT algorithm is required")
        if not self.workload_allowed_algorithms:
            raise ValueError("at least one workload JWT algorithm is required")
        if not set(self.allowed_algorithms).issubset(_ASYMMETRIC_JWT_ALGORITHMS):
            raise ValueError("user ID Tokens must use approved asymmetric algorithms")
        if not set(self.workload_allowed_algorithms).issubset(
            _ASYMMETRIC_JWT_ALGORITHMS
        ):
            raise ValueError("workload tokens must use approved asymmetric algorithms")
        if not 0 <= self.clock_skew_seconds <= 300:
            raise ValueError("clock skew must be between 0 and 300 seconds")
        if self.targets and not self.workload_discovery_url:
            raise WorkloadBindingError(
                "workload token discovery is required for protected targets"
            )
        if self.targets and not self.expected_workload_issuer:
            raise WorkloadBindingError(
                "the expected workload token issuer is required for protected targets"
            )
        if bool(self.workload_discovery_url) != bool(self.expected_workload_issuer):
            raise WorkloadBindingError(
                "workload token discovery and expected issuer must be configured together"
            )
        if not 1 <= self.jwks_cache_seconds <= 3600:
            raise ValueError("jwks_cache_seconds must be between 1 and 3600")
        if not 1 <= self.workload_jwks_cache_seconds <= 3600:
            raise ValueError("workload_jwks_cache_seconds must be between 1 and 3600")
        if not 1 <= self.max_cached_tokens <= 10_000:
            raise ValueError("max_cached_tokens must be between 1 and 10000")
        normalized: dict[str, ProtectedTarget] = {}
        for alias, target in self.targets.items():
            if alias != target.alias:
                raise ValueError("target mapping key must equal target.alias")
            normalized[alias] = target
        object.__setattr__(self, "workload_id", workload_id)
        object.__setattr__(self, "targets", MappingProxyType(normalized))


class WorkloadTokenExchange(Protocol):
    """Deployment-trusted backend for GetWorkloadAccessTokenForJWT.

    Implementations receive the raw subject token. They belong to AgentKit,
    APIG, or another credential boundary and must never be constructed from
    Agent or Tool input.
    """

    def exchange_for_jwt(
        self,
        *,
        workload_pool: str,
        workload_id: str,
        subject_token: str,
        audience: str,
        duration_seconds: int,
    ) -> tuple[str, Any]: ...
