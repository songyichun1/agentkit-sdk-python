from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentkit_identity import (
    IdentityASGIMiddleware,
    IdentityAuthenticationError,
    IdentityContext,
    RequestBindingDecision,
    current_identity,
)


def _context() -> IdentityContext:
    return IdentityContext(
        user_sub="alice",
        issuer="https://issuer.example.com",
        client_id="client",
        user_expires_at=2_000_000_000,
        runtime_id="r-1",
        workload_pool="default",
        invocation_id="inv-1",
    )


class _Runtime:
    def _authenticate(self, authorization):
        if authorization != "Bearer secret.jwt.value":
            raise IdentityAuthenticationError("invalid")
        return SimpleNamespace(context=_context(), user_token="secret.jwt.value")


class _InvokePolicy:
    def decide(self, request, identity):
        return RequestBindingDecision(
            request.path == "/invoke"
            and request.method == "POST"
            and (request.is_preflight or identity.user_sub == "alice")
        )


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def test_middleware_requires_an_explicit_policy():
    with pytest.raises(TypeError, match="binding policy"):
        IdentityASGIMiddleware(lambda *_: None, identity=_Runtime(), route_policy=None)


def test_middleware_scrubs_credentials_and_resets_context():
    async def exercise():
        seen = {}

        async def app(scope, receive, send):
            seen["headers"] = scope["headers"]
            seen["identity"] = scope["state"]["safe_identity"]
            assert current_identity().user_sub == "alice"
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        messages = []

        async def send(message):
            messages.append(message)

        middleware = IdentityASGIMiddleware(
            app,
            identity=_Runtime(),
            route_policy=_InvokePolicy(),
            state_key="safe_identity",
        )
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/invoke",
                "headers": [(b"authorization", b"Bearer secret.jwt.value")],
            },
            _receive,
            send,
        )
        assert messages[0]["status"] == 200
        assert not any(key == b"authorization" for key, _ in seen["headers"])
        assert seen["identity"].user_sub == "alice"
        assert current_identity(required=False) is None

    asyncio.run(exercise())


def test_policy_failure_and_unknown_route_fail_closed():
    class _FailingPolicy:
        def decide(self, request, identity):
            raise RuntimeError("policy backend failed")

    async def exercise():
        called = False
        messages = []

        async def app(scope, receive, send):
            nonlocal called
            called = True

        async def send(message):
            messages.append(message)

        middleware = IdentityASGIMiddleware(
            app,
            identity=_Runtime(),
            route_policy=_FailingPolicy(),
        )
        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/unknown",
                "headers": [(b"authorization", b"Bearer secret.jwt.value")],
            },
            _receive,
            send,
        )
        assert not called
        assert messages[0]["status"] == 403
        assert b"ROUTE_NOT_IDENTITY_BOUND" in messages[1]["body"]

    asyncio.run(exercise())


def test_inner_exception_traceback_does_not_retain_id_token():
    async def exercise():
        async def app(scope, receive, send):
            raise ValueError("inner application failed")

        async def send(message):
            pass

        middleware = IdentityASGIMiddleware(
            app,
            identity=_Runtime(),
            route_policy=_InvokePolicy(),
        )
        try:
            await middleware(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/invoke",
                    "headers": [(b"authorization", b"Bearer secret.jwt.value")],
                },
                _receive,
                send,
            )
        except ValueError as error:
            traceback = error.__traceback__
            while traceback is not None:
                locals_repr = repr(traceback.tb_frame.f_locals)
                assert "secret.jwt.value" not in locals_repr
                assert "Bearer secret.jwt.value" not in locals_repr
                traceback = traceback.tb_next
        else:
            raise AssertionError("inner application failure did not propagate")

    asyncio.run(exercise())
