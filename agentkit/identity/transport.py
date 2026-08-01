"""Compatibility alias for target-bound identity transport."""

from agentkit.identity._runtime_dependency import require_identity_runtime

AuthorizedSession = require_identity_runtime().AuthorizedSession

__all__ = ["AuthorizedSession"]
