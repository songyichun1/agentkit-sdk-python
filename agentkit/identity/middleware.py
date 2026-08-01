# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Pure ASGI middleware for verified, request-scoped Runtime identity."""

from __future__ import annotations

import json
import re
from typing import Any

from agentkit.identity.context import _bind_identity, _reset_identity
from agentkit.identity.errors import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
)
from agentkit.identity.runtime import RuntimeIdentity

_ADK_USER_PATH = re.compile(r"^/apps/[^/]+/users/([^/]+)(?:/|$)")
_IDENTITY_BOUND_ROUTES = frozenset({"/invoke", "/run_sse"})


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

    async def _call_without_credential(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        child_scope = dict(scope)
        child_scope["headers"] = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() != b"authorization"
        ]
        await self.app(child_scope, receive, send)

    @staticmethod
    def _route_is_bound(scope: dict[str, Any], subject: str) -> bool:
        """Allow only routes whose user ownership is explicit in V1."""

        path = str(scope.get("path") or "")
        if path in _IDENTITY_BOUND_ROUTES:
            return True
        match = _ADK_USER_PATH.match(path)
        return match is not None and match.group(1) == subject

    @staticmethod
    def _preflight_route_is_bound(scope: dict[str, Any]) -> bool:
        path = str(scope.get("path") or "")
        return path in _IDENTITY_BOUND_ROUTES or _ADK_USER_PATH.match(path) is not None

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
            await self.app(scope, receive, send)
            return
        if scope_type == "websocket":
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
            await self._call_without_credential(scope, receive, send)
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
        try:
            authenticated = self.identity._authenticate(self._authorization(scope))
        except IdentityAuthenticationError:
            await self._error(send, 401, "AUTH_REQUIRED")
            return
        except IdentityUnavailableError:
            await self._error(send, 503, "IDENTITY_UNAVAILABLE")
            return

        child_scope = dict(scope)
        child_scope["headers"] = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() != b"authorization"
        ]
        state = dict(scope.get("state") or {})
        context = authenticated.context
        if not self._route_is_bound(scope, context.user_sub):
            code = (
                "SUBJECT_MISMATCH"
                if _ADK_USER_PATH.match(str(scope.get("path") or ""))
                else "ROUTE_NOT_IDENTITY_BOUND"
            )
            await self._error(send, 403, code)
            return
        state["agentkit_identity"] = context
        child_scope["state"] = state

        marker = _bind_identity(
            context,
            owner=self.identity,
            user_token=authenticated.user_token,
        )
        try:
            # A pure ASGI wrapper retains the ContextVar until streaming and
            # cancellation complete; BaseHTTPMiddleware would reset too early.
            await self.app(child_scope, receive, send)
        finally:
            _reset_identity(marker)
