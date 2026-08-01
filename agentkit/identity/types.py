"""Compatibility aliases for public Agent Identity Runtime models."""

from agentkit.identity._runtime_dependency import require_identity_runtime

_runtime = require_identity_runtime()

DelegationReceipt = _runtime.DelegationReceipt
IdentityRuntimeConfig = _runtime.IdentityRuntimeConfig
ProtectedTarget = _runtime.ProtectedTarget
VerifiedUserIdentity = _runtime.VerifiedUserIdentity
WorkloadTokenExchange = _runtime.WorkloadTokenExchange

__all__ = [
    "DelegationReceipt",
    "IdentityRuntimeConfig",
    "ProtectedTarget",
    "VerifiedUserIdentity",
    "WorkloadTokenExchange",
]
