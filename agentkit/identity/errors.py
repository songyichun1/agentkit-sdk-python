"""Compatibility aliases for Agent Identity Runtime errors."""

from agentkit.identity._runtime_dependency import require_identity_runtime

_runtime = require_identity_runtime()

IdentityAuthenticationError = _runtime.IdentityAuthenticationError
IdentityError = _runtime.IdentityError
IdentityUnavailableError = _runtime.IdentityUnavailableError
TargetNotConfiguredError = _runtime.TargetNotConfiguredError
TargetRequestError = _runtime.TargetRequestError
TokenExchangeError = _runtime.TokenExchangeError
WorkloadBindingError = _runtime.WorkloadBindingError

__all__ = [
    "IdentityAuthenticationError",
    "IdentityError",
    "IdentityUnavailableError",
    "TargetNotConfiguredError",
    "TargetRequestError",
    "TokenExchangeError",
    "WorkloadBindingError",
]
