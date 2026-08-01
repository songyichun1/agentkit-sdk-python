"""Compatibility aliases for Agent Identity Runtime JWT verifiers."""

from agentkit.identity._runtime_dependency import require_identity_runtime

_runtime = require_identity_runtime()

OidcJwtVerifier = _runtime.OidcJwtVerifier
WorkloadJwtVerifier = _runtime.WorkloadJwtVerifier

__all__ = ["OidcJwtVerifier", "WorkloadJwtVerifier"]
