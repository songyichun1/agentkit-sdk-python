"""Compatibility aliases for the token-free Runtime identity context."""

from agentkit.identity._runtime_dependency import require_identity_runtime

_runtime = require_identity_runtime()

IdentityContext = _runtime.IdentityContext
current_identity = _runtime.current_identity

__all__ = ["IdentityContext", "current_identity"]
