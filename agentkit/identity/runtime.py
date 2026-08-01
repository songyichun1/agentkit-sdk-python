"""Compatibility alias for the canonical Runtime identity implementation."""

from agentkit.identity._runtime_dependency import require_identity_runtime

RuntimeIdentity = require_identity_runtime().RuntimeIdentity

__all__ = ["RuntimeIdentity"]
