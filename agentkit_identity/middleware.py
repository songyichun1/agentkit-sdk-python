# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Framework-neutral ASGI identity request-scope enforcement."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from agentkit_identity.context import _bind_identity, _drain_identity, _reset_identity
from agentkit_identity.errors import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
)
from agentkit_identity.runtime import RuntimeIdentity

_SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SAFE_STATE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class SafeRequestDescriptor:
    """Credential-free request facts supplied to a framework route policy."""

    scope_type: str
    path: str
    method: str
    is_preflight: bool = False


@dataclass(frozen=True)
class RequestBindingDecision:
    """A fail-closed route decision with a response-safe error code."""

    allowed: bool
    error_code: str = "ROUTE_NOT_IDENTITY_BOUND"

    def __post_init__(self) -> None:
        if _SAFE_ERROR_CODE.fullmatch(self.error_code) is None:
            raise ValueError("route policy error codes must be fixed safe identifiers")


class RequestBindingPolicy(Protocol):
    """Framework-owned authorization for one safe request descriptor."""

    def decide(
        self,
        request: SafeRequestDescriptor,
        identity: Any | None,
    ) -> RequestBindingDecision: ...


@dataclass(frozen=True)
class _AuthenticationFailure:
    status: int
    code: str


class IdentityASGIMiddleware:
    """Verify, scrub, bind and revoke identity around one ASGI request.

    The framework must provide a route policy. Missing policies, policy errors,
    unknown routes and malformed decisions fail closed. Raw bearer credentials
    are retained only inside private package bindings and are removed from the
    scope passed to the business application.
    """

    def __init__(
        self,
        app: Any,
        *,
        identity: RuntimeIdentity,
        route_policy: RequestBindingPolicy,
        public_health_routes: tuple[str, ...] = (),
        state_key: str = "agent_identity",
    ) -> None:
        if route_policy is None:
            raise TypeError("an explicit request binding policy is required")
        self.app = app
        self.identity = identity
        self.route_policy = route_policy
        for path in public_health_routes:
            if (
                not path.startswith("/")
                or path == "/"
                or any(marker in path for marker in ("{", "}", "?", "#"))
            ):
                raise ValueError("public health routes must be fixed absolute paths")
        if _SAFE_STATE_KEY.fullmatch(state_key) is None:
            raise ValueError("identity state key must be a fixed safe identifier")
        self.public_health_routes = frozenset(public_health_routes)
        self.state_key = state_key

    @staticmethod
    def _authorization(scope: dict[str, Any]) -> str | None:
        values = [
            value.decode("latin-1")
            for key, value in scope.get("headers", [])
            if key.lower() == b"authorization"
        ]
        if len(values) != 1:
            return None
        return values[0]

    @staticmethod
    def _is_cors_preflight(scope: dict[str, Any]) -> bool:
        if scope.get("method") != "OPTIONS":
            return False
        names = {key.lower() for key, _ in scope.get("headers", [])}
        return (
            b"origin" in names
            and b"access-control-request-method" in names
            and b"authorization" not in names
            and b"cookie" not in names
        )

    def _is_public_health_route(self, scope: dict[str, Any]) -> bool:
        return (
            scope.get("method") in {"GET", "HEAD"}
            and str(scope.get("path") or "") in self.public_health_routes
        )

    @staticmethod
    def _scope_without_credential(scope: dict[str, Any]) -> dict[str, Any]:
        child_scope = dict(scope)
        child_scope["headers"] = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() != b"authorization"
        ]
        return child_scope

    def _authenticate_result(self, scope: dict[str, Any]) -> Any:
        """Contain raw scope/token frames and return only a safe outcome."""

        try:
            return self.identity._authenticate(self._authorization(scope))
        except IdentityAuthenticationError:
            return _AuthenticationFailure(401, "AUTH_REQUIRED")
        except IdentityUnavailableError:
            return _AuthenticationFailure(503, "IDENTITY_UNAVAILABLE")
        except Exception:  # noqa: BLE001 - discard credential-bearing frames
            return _AuthenticationFailure(503, "IDENTITY_UNAVAILABLE")

    def _bind_authenticated(self, authenticated: Any) -> Any | None:
        """Move the private token into package-owned ContextVar storage."""

        try:
            return _bind_identity(
                authenticated.context,
                owner=self.identity,
                user_token=authenticated.user_token,
            )
        except Exception:  # noqa: BLE001 - discard secret-bearing frames
            return None

    @staticmethod
    def _requested_preflight_method(scope: dict[str, Any]) -> str | None:
        values = [
            value.decode("latin-1").strip().upper()
            for key, value in scope.get("headers", [])
            if key.lower() == b"access-control-request-method"
        ]
        return values[0] if len(values) == 1 and values[0] else None

    @classmethod
    def _descriptor(
        cls,
        scope: dict[str, Any],
        *,
        is_preflight: bool,
    ) -> SafeRequestDescriptor:
        method = str(scope.get("method") or "").upper()
        if method == "OPTIONS":
            method = cls._requested_preflight_method(scope) or ""
        return SafeRequestDescriptor(
            scope_type=str(scope.get("type") or ""),
            path=str(scope.get("path") or ""),
            method=method,
            is_preflight=is_preflight,
        )

    def _decision(
        self,
        request: SafeRequestDescriptor,
        identity: Any | None,
    ) -> RequestBindingDecision:
        try:
            decision = self.route_policy.decide(request, identity)
        except Exception:  # noqa: BLE001 - policy failures are deny
            return RequestBindingDecision(False)
        if not isinstance(decision, RequestBindingDecision):
            return RequestBindingDecision(False)
        return decision

    @staticmethod
    async def _error(send: Any, status: int, code: str) -> None:
        body = json.dumps({"error": code}, separators=(",", ":")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            scope = self._scope_without_credential(scope)
            await self.app(scope, receive, send)
            return
        if scope_type == "websocket":
            scope = self._scope_without_credential(scope)
            await send(
                {
                    "type": "websocket.close",
                    "code": 4403,
                    "reason": "identity-bound WebSocket routes are not supported",
                }
            )
            return
        if scope_type != "http":
            return
        if self._is_public_health_route(scope):
            scope = self._scope_without_credential(scope)
            await self.app(scope, receive, send)
            return

        is_preflight = self._is_cors_preflight(scope)
        if is_preflight and self._authorization(scope) is None:
            descriptor = self._descriptor(scope, is_preflight=True)
            scope = self._scope_without_credential(scope)
            decision = self._decision(descriptor, None)
            if decision.allowed:
                await self.app(scope, receive, send)
            else:
                await self._error(send, 403, decision.error_code)
            return

        authenticated = self._authenticate_result(scope)
        scope = self._scope_without_credential(scope)
        if isinstance(authenticated, _AuthenticationFailure):
            status, code = authenticated.status, authenticated.code
            authenticated = None
            await self._error(send, status, code)
            return

        context = authenticated.context
        marker = self._bind_authenticated(authenticated)
        authenticated = None
        if marker is None:
            await self._error(send, 503, "IDENTITY_UNAVAILABLE")
            return

        try:
            descriptor = self._descriptor(scope, is_preflight=False)
            decision = self._decision(descriptor, context)
            if not decision.allowed:
                await self._error(send, 403, decision.error_code)
                return
            state = dict(scope.get("state") or {})
            state[self.state_key] = context
            scope["state"] = state
            await self.app(scope, receive, send)
        finally:
            _reset_identity(marker)
            await _drain_identity(marker)
