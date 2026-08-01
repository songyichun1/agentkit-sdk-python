# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Runtime identity binding and target-bound OBO token management."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from hashlib import sha256
from threading import RLock
from typing import TYPE_CHECKING, Any

from agentkit_identity.context import IdentityContext, _current_binding, _RequestLease
from agentkit_identity.errors import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
    TargetNotConfiguredError,
    TokenExchangeError,
    WorkloadBindingError,
)
from agentkit_identity.jwt import OidcJwtVerifier, WorkloadJwtVerifier
from agentkit_identity.types import (
    DelegationReceipt,
    IdentityRuntimeConfig,
    ProtectedTarget,
    WorkloadTokenExchange,
)

if TYPE_CHECKING:
    from agentkit_identity.transport import AuthorizedSession


@dataclass(frozen=True, repr=False)
class _AuthenticatedRequest:
    context: IdentityContext
    user_token: str = field(repr=False)


@dataclass(frozen=True, repr=False)
class _IssuedWorkloadToken:
    subject: str
    actor: str
    audiences: tuple[str, ...]
    expires_at: int
    compact: str = field(repr=False)


@dataclass(frozen=True)
class _TokenFailure:
    kind: str


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise IdentityAuthenticationError("a Bearer ID Token is required")
    scheme, separator, credential = authorization.strip().partition(" ")
    if not separator or scheme.lower() != "bearer" or not credential.strip():
        raise IdentityAuthenticationError("a valid Bearer ID Token is required")
    return credential.strip()


def _audiences(claims: dict[str, Any]) -> tuple[str, ...]:
    audience = claims.get("aud")
    if isinstance(audience, str):
        return (audience,)
    if isinstance(audience, list) and all(isinstance(value, str) for value in audience):
        return tuple(audience)
    return ()


def _direct_actor(claims: dict[str, Any]) -> str | None:
    actor = claims.get("act")
    if not isinstance(actor, dict):
        return None
    subject = actor.get("sub")
    return subject if isinstance(subject, str) and subject else None


class RuntimeIdentity:
    """Product Runtime facade for verified inbound identity and ForJWT OBO."""

    def __init__(
        self,
        config: IdentityRuntimeConfig,
        *,
        verifier: OidcJwtVerifier | None = None,
        workload_verifier: WorkloadJwtVerifier | None = None,
        exchange: WorkloadTokenExchange | None = None,
        now: Any = time.time,
    ) -> None:
        if exchange is None and config.targets:
            raise WorkloadBindingError(
                "protected targets require an explicit trusted token exchange"
            )
        self.config = config
        self.verifier = verifier or OidcJwtVerifier(
            discovery_url=config.discovery_url,
            expected_issuer=config.expected_user_issuer,
            allowed_clients=config.allowed_clients,
            allowed_algorithms=config.allowed_algorithms,
            allowed_jwks_origins=config.allowed_jwks_origins,
            clock_skew_seconds=config.clock_skew_seconds,
            jwks_cache_seconds=config.jwks_cache_seconds,
        )
        self.exchange = exchange
        self.workload_verifier = workload_verifier
        if self.workload_verifier is None and config.workload_discovery_url:
            self.workload_verifier = WorkloadJwtVerifier(
                discovery_url=config.workload_discovery_url,
                expected_issuer=config.expected_workload_issuer,
                allowed_algorithms=config.workload_allowed_algorithms,
                allowed_jwks_origins=config.workload_allowed_jwks_origins,
                clock_skew_seconds=config.clock_skew_seconds,
                jwks_cache_seconds=config.workload_jwks_cache_seconds,
            )
        self._now = now
        self._cache: dict[tuple[str, ...], _IssuedWorkloadToken] = {}
        # One lock provides deterministic singleflight semantics in V1.  The
        # Identity exchange is short and cache misses are uncommon.
        self._exchange_lock = RLock()

    def _authenticate(
        self,
        authorization: str | None,
        *,
        invocation_id: str | None = None,
    ) -> _AuthenticatedRequest:
        compact = _bearer_token(authorization)
        verified = self.verifier.verify(compact)
        return _AuthenticatedRequest(
            context=IdentityContext(
                user_sub=verified.subject,
                issuer=verified.issuer,
                client_id=verified.client_id,
                user_expires_at=verified.expires_at,
                runtime_id=self.config.runtime_id,
                workload_pool=self.config.workload_pool,
                invocation_id=invocation_id or str(uuid.uuid4()),
            ),
            user_token=compact,
        )

    def verify_inbound(self, authorization: str | None) -> IdentityContext:
        """Verify inbound identity without retaining its token on failure."""

        outcome = self._verify_inbound_result(authorization)
        authorization = None
        if isinstance(outcome, _TokenFailure):
            if outcome.kind == "unavailable":
                raise IdentityUnavailableError(
                    "inbound identity verification is unavailable"
                ) from None
            raise IdentityAuthenticationError(
                "inbound identity verification failed"
            ) from None
        return outcome

    def _verify_inbound_result(
        self,
        authorization: str | None,
    ) -> IdentityContext | _TokenFailure:
        """Contain every Runtime frame that may retain the inbound token."""

        try:
            return self._authenticate(authorization).context
        except IdentityAuthenticationError:
            return _TokenFailure("authentication")
        except Exception:  # noqa: BLE001 - discard secret-bearing verifier frames
            return _TokenFailure("unavailable")

    def target(self, alias: str) -> ProtectedTarget:
        try:
            return self.config.targets[alias]
        except KeyError:
            raise TargetNotConfiguredError(
                "the requested protected target is not registered"
            ) from None

    def _token_for(self, target_alias: str) -> _IssuedWorkloadToken:
        """Return a target-bound TIP without exposing credential-bearing frames."""

        outcome = self._token_for_result(target_alias)
        if isinstance(outcome, _IssuedWorkloadToken):
            return outcome
        if outcome.kind == "target":
            raise TargetNotConfiguredError(
                "the requested protected target is not registered"
            ) from None
        if outcome.kind == "identity":
            raise IdentityAuthenticationError(
                "no active verified identity is bound to this Runtime request"
            ) from None
        raise TokenExchangeError(
            "Agent Identity could not produce a valid workload access token"
        ) from None

    def _request_lease(self) -> _RequestLease:
        """Return the active lease without exposing its credential-bearing frame."""

        lease = self._request_lease_result()
        if lease is None:
            raise IdentityAuthenticationError(
                "no active verified identity is bound to this Runtime request"
            ) from None
        return lease

    def _request_lease_result(self) -> _RequestLease | None:
        """Contain bindings that privately retain the inbound ID Token."""

        try:
            return _current_binding(self).lease
        except IdentityAuthenticationError:
            return None

    def _token_for_result(
        self, target_alias: str
    ) -> _IssuedWorkloadToken | _TokenFailure:
        """Convert every secret-bearing failure to a token-free result."""

        try:
            return self._token_for_secret(target_alias)
        except TargetNotConfiguredError:
            return _TokenFailure("target")
        except IdentityAuthenticationError:
            return _TokenFailure("identity")
        except Exception:  # noqa: BLE001 - discard frames that can retain credentials
            return _TokenFailure("exchange")

    def _token_for_secret(self, target_alias: str) -> _IssuedWorkloadToken:
        """Perform the exchange inside a frame never exposed on SDK errors."""

        binding = _current_binding(self)
        with binding.lease.use():
            return self._token_for_active_binding(target_alias, binding)

    def _token_for_active_binding(
        self, target_alias: str, binding: Any
    ) -> _IssuedWorkloadToken:
        """Use a credential only while its request lease cannot be revoked."""

        bound = binding.context
        target = self.target(target_alias)
        cache_key = (
            bound.issuer,
            bound.client_id,
            bound.user_sub,
            bound.workload_pool,
            bound.runtime_id,
            target.audience,
            sha256(binding.user_token.encode("utf-8")).hexdigest(),
        )
        with self._exchange_lock:
            now = int(self._now())
            self._prune_cache(now)
            cached = self._cache.get(cache_key)
            if cached is not None and cached.expires_at > now + 15:
                return cached
            remaining_user_lifetime = bound.user_expires_at - now
            if remaining_user_lifetime < 60:
                raise TokenExchangeError(
                    "the authenticated user token expires too soon; refresh login"
                )
            duration_seconds = min(
                self.config.token_duration_seconds,
                remaining_user_lifetime,
            )
            if self.exchange is None:
                raise TokenExchangeError("workload token exchange is not configured")
            compact, _ = self.exchange.exchange_for_jwt(
                workload_pool=bound.workload_pool,
                workload_id=bound.runtime_id,
                subject_token=binding.user_token,
                audience=target.audience,
                duration_seconds=duration_seconds,
            )
            token = self._validate_tip(
                compact,
                expected_subject=bound.user_sub,
                expected_actor=bound.runtime_id,
                expected_audience=target.audience,
                expected_user_expiry=bound.user_expires_at,
                requested_duration=duration_seconds,
            )
            if len(self._cache) >= self.config.max_cached_tokens:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = token
            return token

    def _prune_cache(self, now: int) -> None:
        expired = [key for key, value in self._cache.items() if value.expires_at <= now]
        for key in expired:
            self._cache.pop(key, None)

    def _validate_tip(
        self,
        compact: str,
        *,
        expected_subject: str,
        expected_actor: str,
        expected_audience: str,
        expected_user_expiry: int,
        requested_duration: int,
    ) -> _IssuedWorkloadToken:
        """Cryptographically verify the returned TIP and its request binding."""

        if self.workload_verifier is None:
            raise TokenExchangeError("workload token verification is not configured")
        try:
            claims = self.workload_verifier.verify(
                compact,
                audience=expected_audience,
            )
        except IdentityAuthenticationError:
            raise TokenExchangeError(
                "Identity returned an invalid workload access token"
            ) from None
        subject = claims.get("sub")
        actor = _direct_actor(claims)
        audiences = _audiences(claims)
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        now = int(self._now())
        skew = self.config.clock_skew_seconds
        if subject != expected_subject:
            raise TokenExchangeError("the workload token subject does not match")
        if actor != expected_actor:
            raise TokenExchangeError("the workload token actor does not match")
        if audiences != (expected_audience,):
            raise TokenExchangeError("the workload token audience does not match")
        if not isinstance(issued_at, int) or issued_at > now + skew:
            raise TokenExchangeError("the workload token has an invalid issue time")
        if not isinstance(expires_at, int) or expires_at <= now:
            raise TokenExchangeError("the workload token is expired or undated")
        if expires_at <= issued_at:
            raise TokenExchangeError("the workload token lifetime is invalid")
        if expires_at - issued_at > requested_duration + skew:
            raise TokenExchangeError("the workload token lifetime is too broad")
        if expires_at > expected_user_expiry + skew:
            raise TokenExchangeError(
                "the workload token outlives the delegated user credential"
            )
        return _IssuedWorkloadToken(
            subject=expected_subject,
            actor=expected_actor,
            audiences=audiences,
            expires_at=expires_at,
            compact=compact,
        )

    def clear_cache(self) -> None:
        with self._exchange_lock:
            self._cache.clear()

    def delegation_receipt(self, target_alias: str) -> DelegationReceipt:
        """Return token-free evidence after verifying a target-bound OBO TIP."""

        binding = _current_binding(self)
        token = self._token_for(target_alias)
        return DelegationReceipt(
            target_alias=target_alias,
            subject=token.subject,
            actor=token.actor,
            audience=token.audiences[0],
            expires_at=token.expires_at,
            invocation_id=binding.context.invocation_id,
        )

    def authorized_session(self) -> AuthorizedSession:
        """Build the supported HTTP path for target-bound downstream calls."""

        from agentkit_identity.transport import AuthorizedSession

        return AuthorizedSession(self)
