# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""AgentKit route policy and adapter for the Identity Runtime middleware."""

from __future__ import annotations

import re
from typing import Any

from agentkit.identity._runtime_dependency import require_identity_runtime

_runtime = require_identity_runtime()

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
            r"^/apps/[^/]+/users/([^/]+)/sessions/[^/]+/artifacts/[^/]+/"
            r"versions$"
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


class AgentKitRouteBindingPolicy:
    """Bind only explicitly supported AgentKit and ADK routes."""

    @staticmethod
    def _matched_route_subject(path: str, method: str) -> str | None:
        for pattern, methods in _ADK_USER_ROUTE_RULES:
            match = pattern.fullmatch(path)
            if match is not None and method in methods:
                return match.group(1)
        return None

    def decide(self, request: Any, identity: Any | None) -> Any:
        path = request.path
        method = request.method
        if method in _IDENTITY_BOUND_ROUTES.get(path, ()):
            return _runtime.RequestBindingDecision(True)

        route_subject = self._matched_route_subject(path, method)
        if request.is_preflight:
            return _runtime.RequestBindingDecision(route_subject is not None)
        if route_subject is None:
            return _runtime.RequestBindingDecision(False)
        if identity is None or route_subject != identity.user_sub:
            return _runtime.RequestBindingDecision(False, "SUBJECT_MISMATCH")
        return _runtime.RequestBindingDecision(True)


class AgentIdentityMiddleware(_runtime.IdentityASGIMiddleware):
    """Install the credential kernel with AgentKit's fail-closed route policy."""

    def __init__(
        self,
        app: Any,
        *,
        identity: Any,
        public_health_routes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(
            app,
            identity=identity,
            route_policy=AgentKitRouteBindingPolicy(),
            public_health_routes=public_health_routes,
            state_key="agentkit_identity",
        )


__all__ = ["AgentIdentityMiddleware", "AgentKitRouteBindingPolicy"]
