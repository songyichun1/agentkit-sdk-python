from __future__ import annotations

import pytest

from agentkit.identity import IdentityClient, TokenExchangeError, WorkloadBindingError
from agentkit.identity.client import _AgentIdentityService
from agentkit.platform.configuration import Credentials


class _Service:
    def __init__(self):
        self.action = None
        self.body = None

    def _invoke_api(self, action, request, response_type):
        self.action = action
        self.body = request.model_dump(by_alias=True)
        return response_type(
            WorkloadAccessToken="tip.jwt.value",
            ExpiresAt="2030-01-01T00:00:00Z",
        )


def test_for_jwt_uses_the_agent_identity_request_contract_without_scope():
    service = _Service()
    client = IdentityClient(
        credential_provider=lambda: Credentials("ak", "sk", "sts"),
        service_factory=lambda credentials, region: service,
    )
    compact, expires_at = client.exchange_for_jwt(
        workload_pool="default",
        workload_id="runtime-1",
        subject_token="user.jwt.value",
        audience="trn:customer:bpm-api",
        duration_seconds=300,
    )
    assert compact == "tip.jwt.value"
    assert expires_at == "2030-01-01T00:00:00Z"
    assert service.action == "GetWorkloadAccessTokenForJWT"
    assert service.body == {
        "WorkloadPoolName": "default",
        "Name": "runtime-1",
        "UserToken": "user.jwt.value",
        "Audience": ["trn:customer:bpm-api"],
        "DurationSeconds": 300,
    }


def test_exchange_error_does_not_reproduce_a_secret_from_the_backend():
    secret = "user.jwt.secret"

    class _FailingService:
        def _invoke_api(self, action, request, response_type):
            raise RuntimeError(f"request body contained {secret}")

    client = IdentityClient(
        credential_provider=lambda: Credentials("ak", "sk", "sts"),
        service_factory=lambda credentials, region: _FailingService(),
    )
    with pytest.raises(TokenExchangeError) as error:
        client.exchange_for_jwt(
            workload_pool="default",
            workload_id="runtime-1",
            subject_token=secret,
            audience="trn:customer:bpm-api",
            duration_seconds=300,
        )
    assert secret not in str(error.value)
    assert error.value.__cause__ is None
    traceback = error.value.__traceback__
    while traceback is not None:
        if "/agentkit/" in traceback.tb_frame.f_code.co_filename:
            assert secret not in repr(traceback.tb_frame.f_locals)
        traceback = traceback.tb_next


def test_identity_endpoint_environment_override_is_rejected(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_AGENT_IDENTITY_HOST", "attacker.example.com")
    with pytest.raises(WorkloadBindingError):
        _AgentIdentityService(
            credentials=Credentials("ak", "sk", "sts"),
            region="cn-beijing",
        )
