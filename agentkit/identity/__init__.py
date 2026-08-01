# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""AgentKit Runtime Agent/Workload Identity and OBO primitives.

This top-level package is the Runtime data plane. The existing
``agentkit.sdk.identity`` package remains the management-plane API for inbound
authorizer configuration. Public objects are loaded lazily so importing
``agentkit.auth`` does not pull Runtime, HTTP, Pydantic, or platform clients.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "AgentIdentityMiddleware": (
        "agentkit.identity.middleware",
        "AgentIdentityMiddleware",
    ),
    "AuthorizedSession": ("agentkit.identity.transport", "AuthorizedSession"),
    "DelegationReceipt": ("agentkit.identity.types", "DelegationReceipt"),
    "IdentityAuthenticationError": (
        "agentkit.identity.errors",
        "IdentityAuthenticationError",
    ),
    "IdentityClient": ("agentkit.identity.client", "IdentityClient"),
    "IdentityContext": ("agentkit.identity.context", "IdentityContext"),
    "IdentityError": ("agentkit.identity.errors", "IdentityError"),
    "IdentityRuntimeConfig": ("agentkit.identity.types", "IdentityRuntimeConfig"),
    "IdentityUnavailableError": (
        "agentkit.identity.errors",
        "IdentityUnavailableError",
    ),
    "OidcJwtVerifier": ("agentkit.identity.jwt", "OidcJwtVerifier"),
    "ProtectedTarget": ("agentkit.identity.types", "ProtectedTarget"),
    "RuntimeIdentity": ("agentkit.identity.runtime", "RuntimeIdentity"),
    "TargetNotConfiguredError": (
        "agentkit.identity.errors",
        "TargetNotConfiguredError",
    ),
    "TargetRequestError": (
        "agentkit.identity.errors",
        "TargetRequestError",
    ),
    "TokenExchangeError": ("agentkit.identity.errors", "TokenExchangeError"),
    "VerifiedUserIdentity": ("agentkit.identity.types", "VerifiedUserIdentity"),
    "WorkloadBindingError": ("agentkit.identity.errors", "WorkloadBindingError"),
    "WorkloadJwtVerifier": ("agentkit.identity.jwt", "WorkloadJwtVerifier"),
    "WorkloadTokenExchange": (
        "agentkit.identity.types",
        "WorkloadTokenExchange",
    ),
    "current_identity": ("agentkit.identity.context", "current_identity"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(
            f"module 'agentkit.identity' has no attribute {name!r}"
        ) from None
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


__all__ = list(_EXPORTS)
