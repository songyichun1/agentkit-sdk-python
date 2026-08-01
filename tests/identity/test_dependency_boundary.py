from __future__ import annotations

from typing import get_type_hints

import agentkit_identity
import pytest

from agentkit import identity as compatibility
from agentkit.apps.agent_server_app.agent_server_app import AgentkitAgentServerApp
from agentkit.identity import _runtime_dependency


@pytest.mark.parametrize(
    "name",
    [
        "AuthorizedSession",
        "DelegationReceipt",
        "IdentityAuthenticationError",
        "IdentityContext",
        "IdentityError",
        "IdentityRuntimeConfig",
        "IdentityUnavailableError",
        "OidcJwtVerifier",
        "ProtectedTarget",
        "RuntimeIdentity",
        "TargetNotConfiguredError",
        "TargetRequestError",
        "TokenExchangeError",
        "VerifiedUserIdentity",
        "WorkloadBindingError",
        "WorkloadJwtVerifier",
        "WorkloadTokenExchange",
        "current_identity",
    ],
)
def test_legacy_exports_are_the_canonical_runtime_objects(name):
    assert getattr(compatibility, name) is getattr(agentkit_identity, name)


def test_missing_bundled_runtime_has_an_actionable_fail_closed_error(monkeypatch):
    real_import = _runtime_dependency.import_module

    def missing(name):
        if name == "agentkit_identity":
            error = ModuleNotFoundError("missing bundled runtime")
            error.name = "agentkit_identity"
            raise error
        return real_import(name)

    monkeypatch.setattr(_runtime_dependency, "import_module", missing)
    with pytest.raises(RuntimeError, match="Reinstall.*agentkit-sdk-python"):
        _runtime_dependency.require_identity_runtime()


def test_transitive_import_failure_is_not_misreported_as_missing_runtime(monkeypatch):
    def broken(name):
        error = ModuleNotFoundError("missing cryptography")
        error.name = "cryptography"
        raise error

    monkeypatch.setattr(_runtime_dependency, "import_module", broken)
    with pytest.raises(ModuleNotFoundError, match="cryptography"):
        _runtime_dependency.require_identity_runtime()


def test_identity_annotation_can_be_introspected_without_eager_import():
    hints = get_type_hints(AgentkitAgentServerApp.__init__)
    assert hints["identity"] is not None
