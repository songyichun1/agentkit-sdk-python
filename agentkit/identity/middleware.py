# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Pure ASGI middleware for verified, request-scoped Runtime identity."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from agentkit.identity.context import _bind_identity, _drain_identity, _reset_identity
from agentkit.identity.errors import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
)
from agentkit.identity.runtime import RuntimeIdentity

_IDENTITY_BOUND_ROUTES = {
    "/invoke": frozenset({"POST"}),
    "/run_sse": frozenset({"POST"}),
}
_ADK_USER_ROUTE_RULES = (
    (re.compile(r"^/apps/[^/]+/users/([^/]+)/sessions$"), {"GET", "POST"}),
    (
        re.compile(r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+$"),
        {"GET", "POST", "DELETE", "PATCH"},
    ),
    (
        re.compile(r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts$"),
        {"GET", "POST"},
    ),
    (
        re.compile(r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts/[^/]+$"),
        {"GET", "DELETE"},
    ),
    (
        re.compile(
            r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts/[^/]+/versions$"
        ),
        {"GET"},
    ),
    (
        re.compile(
            r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts/[^/]+/"
            r"versions/metadata$"
        ),
        {"GET"},
    ),
    (
        re.compile(
            r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts/[^/]+/"
            r"versions/[^/]+$"
        ),
        {"GET"},
    ),
    (
        re.compile(
            r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts/[^/]+/"
            r"versions/[^/]+/metadata$"
        ),
        {"GET"},
    ),
    (re.compile(r"^/apps/[^/]+/users/([^/]+)/memory$"), {"PATCH"}),
)


@dataclass(frozen=True)
class _AuthenticationFailure:
    status: int
    code: str


class AgentIdentityMiddleware:
    """Verify the inbound ID Token before any Agent route executes.

    A copied ASGI scope with the Authorization header removed is passed to the
    business application. The original token is kept in a separate private SDK
    binding and is not present in ``current_identity()`` or request state.
    """

    def __init__(
        self,
        app: Any,
        *,
        identity: RuntimeIdentity,
        public_health_routes: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.identity = identity
        for path in public_health_routes:
            if (
                not path.startswith("/")
                or path == "/"
                or any(marker in path for marker in ("{", "}", "?", "#"))
            ):
                raise ValueError("public health routes must be fixed absolute paths")
        self.public_health_routes = frozenset(public_health_routes)

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
        except Exception:  # noqa: BLE001 - discard frames that can retain credentials
            return _AuthenticationFailure(503, "IDENTITY_UNAVAILABLE")

    def _bind_authenticated(self, authenticated: Any) -> Any | None:
        """Move the private token into ContextVar storage without leaking frames."""

        try:
            return _bind_identity(
                authenticated.context,
                owner=self.identity,
                user_token=authenticated.user_token,
            )
        except Exception:  # noqa: BLE001 - discard secret-bearing binding frames
            return None

    @staticmethod
    def _requested_preflight_method(scope: dict[str, Any]) -> str | None:
        values = [
            value.decode("latin-1").strip().upper()
            for key, value in scope.get("headers", [])
            if key.lower() == b"access-control-request-method"
        ]
        return values[0] if len(values) == 1 and values[0] else None

    @staticmethod
    def _matched_route_subject(path: str, method: str) -> str | None:
        for pattern, methods in _ADK_USER_ROUTE_RULES:
            match = pattern.fullmatch(path)
            if match is not None and method in methods:
                return match.group(1)
        return None

    @classmethod
    def _route_is_bound(cls, scope: dict[str, Any], subject: str) -> bool:
        """Allow only routes whose user ownership is explicit in V1."""

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "").upper()
        if method == "OPTIONS":
            method = cls._requested_preflight_method(scope) or ""
        if method in _IDENTITY_BOUND_ROUTES.get(path, ()):
            return True
        return cls._matched_route_subject(path, method) == subject

    @classmethod
    def _preflight_route_is_bound(cls, scope: dict[str, Any]) -> bool:
        path = str(scope.get("path") or "")
        method = cls._requested_preflight_method(scope)
        if method is None:
            return False
        return method in _IDENTITY_BOUND_ROUTES.get(path, ()) or (
            cls._matched_route_subject(path, method) is not None
        )

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
            # Fixed, deployment-selected liveness/readiness routes perform no
            # business action. Never expose a caller credential to them.
            scope = self._scope_without_credential(scope)
            await self.app(scope, receive, send)
            return
        if self._is_cors_preflight(scope) and self._authorization(scope) is None:
            # Browser preflight carries no user credential and performs no
            # business action. The inner CORS middleware (or router) decides
            # whether this origin/method is allowed.
            if self._preflight_route_is_bound(scope):
                await self.app(scope, receive, send)
            else:
                await self._error(send, 403, "ROUTE_NOT_IDENTITY_BOUND")
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
            if not self._route_is_bound(scope, context.user_sub):
                path = str(scope.get("path") or "")
                method = str(scope.get("method") or "").upper()
                if method == "OPTIONS":
                    method = self._requested_preflight_method(scope) or ""
                code = (
                    "SUBJECT_MISMATCH"
                    if self._matched_route_subject(path, method) is not None
                    else "ROUTE_NOT_IDENTITY_BOUND"
                )
                await self._error(send, 403, code)
                return
            state = dict(scope.get("state") or {})
            state["agentkit_identity"] = context
            scope["state"] = state

            # A pure ASGI wrapper retains the ContextVar until streaming and
            # cancellation complete; BaseHTTPMiddleware would reset too early.
            await self.app(scope, receive, send)
        finally:
            _reset_identity(marker)
            await _drain_identity(marker)
