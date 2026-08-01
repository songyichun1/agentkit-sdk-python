# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Verified Runtime identity, OBO and target-bound transport primitives."""

from agentkit_identity.context import IdentityContext, current_identity
from agentkit_identity.errors import (
    IdentityAuthenticationError,
    IdentityError,
    IdentityUnavailableError,
    TargetNotConfiguredError,
    TargetRequestError,
    TokenExchangeError,
    WorkloadBindingError,
)
from agentkit_identity.jwt import OidcJwtVerifier, WorkloadJwtVerifier
from agentkit_identity.middleware import (
    IdentityASGIMiddleware,
    RequestBindingDecision,
    RequestBindingPolicy,
    SafeRequestDescriptor,
)
from agentkit_identity.runtime import RuntimeIdentity
from agentkit_identity.transport import AuthorizedSession
from agentkit_identity.types import (
    DelegationReceipt,
    IdentityRuntimeConfig,
    ProtectedTarget,
    VerifiedUserIdentity,
    WorkloadTokenExchange,
)

__all__ = [
    "AuthorizedSession",
    "DelegationReceipt",
    "IdentityASGIMiddleware",
    "IdentityAuthenticationError",
    "IdentityContext",
    "IdentityError",
    "IdentityRuntimeConfig",
    "IdentityUnavailableError",
    "OidcJwtVerifier",
    "ProtectedTarget",
    "RequestBindingDecision",
    "RequestBindingPolicy",
    "RuntimeIdentity",
    "SafeRequestDescriptor",
    "TargetNotConfiguredError",
    "TargetRequestError",
    "TokenExchangeError",
    "VerifiedUserIdentity",
    "WorkloadBindingError",
    "WorkloadJwtVerifier",
    "WorkloadTokenExchange",
    "current_identity",
]
