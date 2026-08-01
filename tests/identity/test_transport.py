from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from agentkit.identity import AuthorizedSession, ProtectedTarget, TargetRequestError


class _Identity:
    def target(self, alias):
        assert alias == "bpm"
        return ProtectedTarget(
            alias="bpm",
            audience="trn:customer:bpm-api",
            base_url="https://gateway.example.com/bpm",
        )

    def _token_for(self, alias):
        assert alias == "bpm"
        return SimpleNamespace(compact="tip.jwt.secret")


class _Session:
    def __init__(self):
        self.kwargs = None

    def request(self, method, url, **kwargs):
        self.kwargs = {"method": method, "url": url, **kwargs}
        response = requests.Response()
        response.status_code = 200
        response.request = requests.Request(
            method, url, headers=kwargs["headers"]
        ).prepare()
        return response


def test_authorized_session_injects_tip_and_disables_redirects(monkeypatch):
    session = _Session()
    monkeypatch.setattr("agentkit.identity.transport.requests.Session", lambda: session)
    client = AuthorizedSession(_Identity())
    response = client.request(
        "POST", "bpm", "/expenses/123", json={"status": "approved"}
    )
    assert session.kwargs["url"] == "https://gateway.example.com/bpm/expenses/123"
    assert session.kwargs["headers"]["Authorization"] == "Bearer tip.jwt.secret"
    assert session.kwargs["allow_redirects"] is False
    assert response.request is None


def test_business_code_cannot_override_authorization_or_target_host(monkeypatch):
    monkeypatch.setattr(
        "agentkit.identity.transport.requests.Session", lambda: _Session()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(ValueError):
        client.request(
            "GET",
            "bpm",
            "/expenses",
            headers={"authorization": "Bearer attacker"},
        )
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "https://attacker.example.com/")
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "../admin")
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "%2e%2e/admin")


@pytest.mark.parametrize(
    "header",
    [
        "Host",
        "FORWARDED",
        "x-Forwarded-host",
        "X-Original-URL",
        "x-rewrite-url",
        "Cookie",
        "Proxy-Authorization",
    ],
)
def test_business_code_cannot_override_routing_or_credentials(monkeypatch, header):
    monkeypatch.setattr(
        "agentkit.identity.transport.requests.Session", lambda: _Session()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "/expenses", headers={header: "attacker"})


@pytest.mark.parametrize("method", ["TRACE", "trace", "CONNECT"])
def test_reflective_and_tunneling_methods_are_rejected(monkeypatch, method):
    monkeypatch.setattr(
        "agentkit.identity.transport.requests.Session", lambda: _Session()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(ValueError):
        client.request(method, "bpm", "/expenses")


@pytest.mark.parametrize("option", ["auth", "verify", "proxies", "hooks", "cookies"])
def test_business_code_cannot_override_security_transport_options(monkeypatch, option):
    monkeypatch.setattr(
        "agentkit.identity.transport.requests.Session", lambda: _Session()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "/expenses", **{option: object()})


def test_request_exception_is_rebuilt_without_prepared_request(monkeypatch):
    class _FailingSession(_Session):
        def request(self, method, url, **kwargs):
            prepared = requests.Request(
                method, url, headers=kwargs["headers"]
            ).prepare()
            raise requests.ConnectionError("Bearer tip.jwt.secret", request=prepared)

    monkeypatch.setattr(
        "agentkit.identity.transport.requests.Session", lambda: _FailingSession()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(TargetRequestError) as caught:
        client.request("GET", "bpm", "/expenses")
    assert "tip.jwt.secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert not hasattr(caught.value, "request")
    traceback = caught.value.__traceback__
    while traceback is not None:
        if "/agentkit/" in traceback.tb_frame.f_code.co_filename:
            assert "tip.jwt.secret" not in repr(traceback.tb_frame.f_locals)
        traceback = traceback.tb_next


def test_transport_rejects_all_response_cookies():
    client = AuthorizedSession(_Identity())
    policy = client._session.cookies._policy
    assert policy.set_ok(None, None) is False
    assert policy.return_ok(None, None) is False
