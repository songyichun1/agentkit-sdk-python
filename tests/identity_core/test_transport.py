from __future__ import annotations

import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import requests

from agentkit_identity import AuthorizedSession, ProtectedTarget, TargetRequestError


class _Identity:
    def __init__(self):
        self.lease = _Lease()
        self.token_calls = 0

    def target(self, alias):
        assert alias == "bpm"
        return ProtectedTarget(
            alias="bpm",
            audience="trn:customer:bpm-api",
            base_url="https://gateway.example.com/bpm",
        )

    def _token_for(self, alias):
        assert alias == "bpm"
        self.token_calls += 1
        return SimpleNamespace(compact="tip.jwt.secret")

    def _request_lease(self):
        return self.lease


class _Lease:
    def __init__(self):
        self.active = True
        self.uses = 0
        self.condition = threading.Condition()

    @contextmanager
    def use(self):
        with self.condition:
            if not self.active:
                raise RuntimeError("revoked")
            self.uses += 1
        try:
            yield
        finally:
            with self.condition:
                self.uses -= 1
                self.condition.notify_all()

    def revoke(self):
        with self.condition:
            self.active = False

    def wait_idle(self):
        with self.condition:
            while self.uses:
                self.condition.wait()


class _Session:
    def __init__(self):
        self.kwargs = None

    def request(self, method, url, **kwargs):
        self.kwargs = {
            "method": method,
            "url": url,
            **kwargs,
            "headers": dict(kwargs["headers"]),
        }
        response = requests.Response()
        response.status_code = 200
        response._content = b"ok"
        response._content_consumed = True
        response.request = requests.Request(
            method, url, headers=kwargs["headers"]
        ).prepare()
        return response


def test_authorized_session_injects_tip_and_disables_redirects(monkeypatch):
    session = _Session()
    monkeypatch.setattr("agentkit_identity.transport.requests.Session", lambda: session)
    client = AuthorizedSession(_Identity())
    response = client.request(
        "POST", "bpm", "/expenses/123", json={"status": "approved"}
    )
    assert session.kwargs["url"] == "https://gateway.example.com/bpm/expenses/123"
    assert session.kwargs["headers"]["Authorization"] == "Bearer tip.jwt.secret"
    assert session.kwargs["allow_redirects"] is False
    assert response.request is None
    assert response.content == b"ok"


def test_response_cannot_return_an_unmanaged_cookie_credential(monkeypatch):
    class _CookieResponseSession(_Session):
        def request(self, method, url, **kwargs):
            response = super().request(method, url, **kwargs)
            response.headers["Set-Cookie"] = "legacy_session=secret"
            response.headers["Set-Cookie2"] = "legacy_v2=secret"
            response.cookies.set("legacy_session", "secret")
            response.raw = SimpleNamespace(
                headers={"Set-Cookie": "legacy_session=secret"}
            )
            return response

    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session",
        lambda: _CookieResponseSession(),
    )
    response = AuthorizedSession(_Identity()).request("GET", "bpm", "/expenses")
    assert not response.cookies
    assert "Set-Cookie" not in response.headers
    assert "Set-Cookie2" not in response.headers
    assert response.request is None
    assert response.raw is None


def test_business_code_cannot_override_authorization_or_target_host(monkeypatch):
    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _Session()
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
        "Connection",
        "Content-Length",
        "Proxy-Connection",
        "TE",
        "Trailer",
        "Transfer-Encoding",
        "Upgrade",
    ],
)
def test_business_code_cannot_override_routing_or_credentials(monkeypatch, header):
    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _Session()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "/expenses", headers={header: "attacker"})


@pytest.mark.parametrize("method", ["TRACE", "trace", "CONNECT"])
def test_reflective_and_tunneling_methods_are_rejected(monkeypatch, method):
    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _Session()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(ValueError):
        client.request(method, "bpm", "/expenses")


@pytest.mark.parametrize(
    "option", ["auth", "verify", "proxies", "hooks", "cookies", "stream"]
)
def test_business_code_cannot_override_security_transport_options(monkeypatch, option):
    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _Session()
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
        "agentkit_identity.transport.requests.Session", lambda: _FailingSession()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(TargetRequestError) as caught:
        client.request("GET", "bpm", "/expenses")
    assert "tip.jwt.secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert not hasattr(caught.value, "request")
    traceback = caught.value.__traceback__
    matched = 0
    while traceback is not None:
        if "/agentkit_identity/" in traceback.tb_frame.f_code.co_filename:
            matched += 1
            assert "tip.jwt.secret" not in repr(traceback.tb_frame.f_locals)
        traceback = traceback.tb_next
    assert matched > 0


def test_non_requests_exception_is_rebuilt_without_tip_traceback(monkeypatch):
    class _FailingSession(_Session):
        def request(self, method, url, **kwargs):
            raise ValueError(f"unexpected body failure: {kwargs['headers']}")

    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _FailingSession()
    )
    client = AuthorizedSession(_Identity())
    with pytest.raises(TargetRequestError) as caught:
        client.request("POST", "bpm", "/expenses", data=iter([b"body"]))
    assert "tip.jwt.secret" not in str(caught.value)
    traceback = caught.value.__traceback__
    matched = 0
    while traceback is not None:
        if "/agentkit_identity/" in traceback.tb_frame.f_code.co_filename:
            matched += 1
            assert "tip.jwt.secret" not in repr(traceback.tb_frame.f_locals)
        traceback = traceback.tb_next
    assert matched > 0


@pytest.mark.parametrize("timeout", [0, -1, 301, float("inf"), True, "30"])
def test_invalid_timeout_is_rejected_before_tip_acquisition(monkeypatch, timeout):
    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _Session()
    )
    identity = _Identity()
    client = AuthorizedSession(identity)
    with pytest.raises(ValueError):
        client.request("GET", "bpm", "/expenses", timeout=timeout)
    assert identity.token_calls == 0


def test_request_lease_covers_token_injection_through_send(monkeypatch):
    entered_send = threading.Event()
    release_send = threading.Event()

    class _BlockingSession(_Session):
        def request(self, method, url, **kwargs):
            entered_send.set()
            assert release_send.wait(timeout=2)
            return super().request(method, url, **kwargs)

    monkeypatch.setattr(
        "agentkit_identity.transport.requests.Session", lambda: _BlockingSession()
    )
    identity = _Identity()
    client = AuthorizedSession(identity)
    result = {}

    def invoke():
        result["response"] = client.request("GET", "bpm", "/expenses")

    worker = threading.Thread(target=invoke)
    worker.start()
    assert entered_send.wait(timeout=2)
    identity.lease.revoke()
    drained = threading.Event()

    def wait_idle():
        identity.lease.wait_idle()
        drained.set()

    waiter = threading.Thread(target=wait_idle)
    waiter.start()
    assert not drained.wait(timeout=0.05)
    release_send.set()
    worker.join(timeout=2)
    waiter.join(timeout=2)
    assert drained.is_set()
    assert result["response"].status_code == 200


def test_transport_rejects_all_response_cookies():
    client = AuthorizedSession(_Identity())
    policy = client._session.cookies._policy
    assert policy.set_ok(None, None) is False
    assert policy.return_ok(None, None) is False
