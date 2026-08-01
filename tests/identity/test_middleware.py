from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agentkit.identity import AgentIdentityMiddleware
from agentkit.identity.context import IdentityContext, current_identity
from agentkit.identity.errors import IdentityAuthenticationError


def _context():
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


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def test_middleware_scrubs_authorization_and_resets_context():
    asyncio.run(_exercise_middleware_scrubs_authorization_and_resets_context())


async def _exercise_middleware_scrubs_authorization_and_resets_context():
    seen = {}

    async def app(scope, receive, send):
        seen["headers"] = scope["headers"]
        seen["identity"] = current_identity()
        assert scope["state"]["agentkit_identity"].user_sub == "alice"
        assert not hasattr(scope["state"]["agentkit_identity"], "_user_token")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        assert current_identity().user_sub == "alice"
        await send({"type": "http.response.body", "body": b"ok"})

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "path": "/invoke",
            "headers": [(b"authorization", b"Bearer secret.jwt.value")],
        },
        _receive,
        send,
    )
    assert seen["identity"].user_sub == "alice"
    assert not any(key == b"authorization" for key, _ in seen["headers"])
    assert current_identity(required=False) is None
    assert messages[0]["status"] == 200


def test_middleware_rejects_missing_token_before_app():
    asyncio.run(_exercise_middleware_rejects_missing_token_before_app())


async def _exercise_middleware_rejects_missing_token_before_app():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware({"type": "http", "headers": []}, _receive, send)
    assert not called
    assert messages[0]["status"] == 401


def test_fixed_public_health_route_needs_no_token_and_scrubs_one_if_present():
    asyncio.run(_exercise_fixed_public_health_route())


async def _exercise_fixed_public_health_route():
    seen = {}

    async def app(scope, receive, send):
        seen["headers"] = scope["headers"]
        assert current_identity(required=False) is None
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(
        app,
        identity=_Runtime(),
        public_health_routes=("/ping",),
    )
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/ping",
            "headers": [(b"authorization", b"Bearer must-not-reach-health")],
        },
        _receive,
        send,
    )
    assert messages[0]["status"] == 200
    assert not any(key == b"authorization" for key, _ in seen["headers"])


def test_public_health_route_is_exact_and_read_only():
    for method, path in (("POST", "/ping"), ("GET", "/ping/debug")):
        messages = []

        async def app(scope, receive, send):
            raise AssertionError("unbound health route reached business app")

        async def send(message, sink=messages):
            sink.append(message)

        middleware = AgentIdentityMiddleware(
            app,
            identity=_Runtime(),
            public_health_routes=("/ping",),
        )
        asyncio.run(
            middleware(
                {"type": "http", "method": method, "path": path, "headers": []},
                _receive,
                send,
            )
        )
        assert messages[0]["status"] == 401


def test_public_health_route_configuration_rejects_patterns():
    for path in ("ping", "/", "/health/{name}", "/health?full=true"):
        try:
            AgentIdentityMiddleware(
                lambda *_: None,
                identity=_Runtime(),
                public_health_routes=(path,),
            )
        except ValueError:
            continue
        raise AssertionError(f"unsafe public health route accepted: {path}")


def test_middleware_leaves_credential_free_cors_preflight_to_the_inner_app():
    asyncio.run(_exercise_cors_preflight())


async def _exercise_cors_preflight():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True
        assert current_identity(required=False) is None
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "method": "OPTIONS",
            "path": "/invoke",
            "headers": [
                (b"origin", b"https://client.example.com"),
                (b"access-control-request-method", b"POST"),
            ],
        },
        _receive,
        send,
    )
    assert called
    assert messages[0]["status"] == 204


def test_credential_bearing_options_is_authenticated_and_scrubbed():
    asyncio.run(_exercise_credential_bearing_options())


async def _exercise_credential_bearing_options():
    seen = {}

    async def app(scope, receive, send):
        seen["headers"] = scope["headers"]
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "method": "OPTIONS",
            "path": "/invoke",
            "headers": [
                (b"origin", b"https://client.example.com"),
                (b"access-control-request-method", b"POST"),
                (b"authorization", b"Bearer secret.jwt.value"),
            ],
        },
        _receive,
        send,
    )
    assert messages[0]["status"] == 204
    assert not any(key == b"authorization" for key, _ in seen["headers"])


def test_adk_session_path_must_match_verified_subject():
    asyncio.run(_exercise_adk_subject_mismatch())


async def _exercise_adk_subject_mismatch():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/apps/demo/users/bob/sessions/s-1",
            "headers": [(b"authorization", b"Bearer secret.jwt.value")],
        },
        _receive,
        send,
    )
    assert not called
    assert messages[0]["status"] == 403


def test_unbound_adk_run_route_fails_closed():
    asyncio.run(_exercise_unbound_run_route())


async def _exercise_unbound_run_route():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/run",
            "headers": [(b"authorization", b"Bearer secret.jwt.value")],
        },
        _receive,
        send,
    )
    assert not called
    assert messages[0]["status"] == 403
    assert b"ROUTE_NOT_IDENTITY_BOUND" in messages[1]["body"]


def test_debug_and_future_routes_fail_closed():
    asyncio.run(_exercise_unbound_debug_route())


async def _exercise_unbound_debug_route():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": "/debug/trace/session-1",
            "headers": [(b"authorization", b"Bearer secret.jwt.value")],
        },
        _receive,
        send,
    )
    assert not called
    assert messages[0]["status"] == 403
    assert b"ROUTE_NOT_IDENTITY_BOUND" in messages[1]["body"]


def test_unbound_preflight_fails_closed():
    asyncio.run(_exercise_unbound_preflight())


async def _exercise_unbound_preflight():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "http",
            "method": "OPTIONS",
            "path": "/eval_sets",
            "headers": [
                (b"origin", b"https://client.example.com"),
                (b"access-control-request-method", b"POST"),
            ],
        },
        _receive,
        send,
    )
    assert not called
    assert messages[0]["status"] == 403


def test_websocket_fails_closed_before_application():
    asyncio.run(_exercise_websocket_fails_closed())


async def _exercise_websocket_fails_closed():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    messages = []

    async def send(message):
        messages.append(message)

    middleware = AgentIdentityMiddleware(app, identity=_Runtime())
    await middleware(
        {
            "type": "websocket",
            "path": "/run_live",
            "headers": [(b"authorization", b"Bearer secret.jwt.value")],
        },
        _receive,
        send,
    )
    assert not called
    assert messages == [
        {
            "type": "websocket.close",
            "code": 4403,
            "reason": "identity-bound WebSocket routes are not supported",
        }
    ]
