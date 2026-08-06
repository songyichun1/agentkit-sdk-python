# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import inspect

import pytest
from a2a.extensions.common import HTTP_EXTENSION_HEADER
from google.adk.a2a.agent.interceptors.new_integration_extension import (
    _NEW_A2A_ADK_INTEGRATION_EXTENSION,
)
from google.adk.agents.base_agent import BaseAgent
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
)
from google.adk.auth.credential_service.base_credential_service import (
    BaseCredentialService,
)
from starlette.testclient import TestClient

import agentkit.apps.auth.inbound as shared_inbound_auth
from agentkit.apps.agent_server_app.agent_server_app import AgentkitAgentServerApp
from agentkit.apps.agent_server_app.credential_service import (
    AgentkitCredentialService,
)
from agentkit.apps.agent_server_app.inbound_auth import (
    INBOUND_AUTH_CREDENTIAL_KEY,
    TIP_TOKEN_CREDENTIAL_KEY,
    extract_inbound_auth,
    redact_inbound_auth_headers,
    save_inbound_auth,
    strip_bearer,
)


class _InvocationContext:
    app_name = "app_1"
    user_id = "user_1"


class _CallbackContext:
    _invocation_context = _InvocationContext()


class _AuthConfig:
    credential_key = "credential_1"
    exchanged_auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.API_KEY,
        api_key="saved",
    )


class _FallbackAuthConfig:
    exchanged_auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.API_KEY,
        api_key="fallback",
    )

    def get_credential_key(self):
        return "fallback_key"


class _Headers:
    def __init__(self, data: dict[str, str]) -> None:
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)


class _Request:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = _Headers(headers)


def test_strip_bearer_handles_bearer_and_non_bearer_values():
    assert strip_bearer("Bearer abc") == ("abc", True)
    assert strip_bearer(" bearer   abc  ") == ("abc", True)
    assert strip_bearer("abc") == ("abc", False)
    assert strip_bearer("   ") == ("", False)


def test_agentkit_credential_service_direct_and_adk_protocol_access():
    service = AgentkitCredentialService()
    credential = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(
            scheme="bearer",
            credentials=HttpCredentials(token="token_1"),
        ),
    )

    assert isinstance(service, BaseCredentialService)
    asyncio.run(
        service.set_credential(
            app_name="app_1",
            user_id="user_1",
            credential_key="credential_1",
            credential=credential,
        )
    )
    asyncio.run(
        service.set_credential(
            "app_1",
            "user_1",
            "positional_key",
            AuthCredential(
                auth_type=AuthCredentialTypes.API_KEY,
                api_key="positional",
            ),
        )
    )

    loaded = asyncio.run(service.load_credential(_AuthConfig(), _CallbackContext()))
    assert loaded is credential
    positional = asyncio.run(
        service.get_credential("app_1", "user_1", "positional_key")
    )
    assert positional.api_key == "positional"

    asyncio.run(service.save_credential(_FallbackAuthConfig(), _CallbackContext()))
    fallback = asyncio.run(
        service.get_credential(
            app_name="app_1",
            user_id="user_1",
            credential_key="fallback_key",
        )
    )
    assert fallback.api_key == "fallback"


def test_save_inbound_auth_stores_compatible_authorization_and_tip_credentials():
    service = AgentkitCredentialService()
    request = _Request(
        {
            "authorization": "Bearer user-token",
            "X-Ve-TIP-Token": "tip-token",
        }
    )

    asyncio.run(
        save_inbound_auth(
            request=request,
            app_name="app_1",
            user_id="user_1",
            credential_service=service,
        )
    )

    auth_credential = asyncio.run(
        service.get_credential(
            app_name="app_1",
            user_id="user_1",
            credential_key=INBOUND_AUTH_CREDENTIAL_KEY,
        )
    )
    tip_credential = asyncio.run(
        service.get_credential(
            app_name="app_1",
            user_id="user_1",
            credential_key=TIP_TOKEN_CREDENTIAL_KEY,
        )
    )
    assert isinstance(auth_credential, AuthCredential)
    assert auth_credential.auth_type == AuthCredentialTypes.HTTP
    assert auth_credential.http.scheme == "bearer"
    assert auth_credential.http.credentials.token == "user-token"
    assert isinstance(tip_credential, AuthCredential)
    assert tip_credential.auth_type == AuthCredentialTypes.API_KEY
    assert tip_credential.api_key == "tip-token"


def test_save_inbound_auth_fails_open_without_set_credential(caplog):
    request = _Request({"Authorization": "Bearer user-token"})

    asyncio.run(
        save_inbound_auth(
            request=request,
            app_name="app_1",
            user_id="user_1",
            credential_service=object(),
        )
    )

    assert "cannot store inbound auth credentials" in caplog.text
    assert "user-token" not in caplog.text


def test_shared_inbound_auth_module_does_not_import_adk_or_veadk():
    source = inspect.getsource(shared_inbound_auth)

    assert "google.adk" not in source
    assert "veadk" not in source


def test_extract_inbound_auth_and_redaction_are_framework_neutral():
    headers = {
        "AuthoriZation": "Bearer user-token",
        "X-Ve-Tip-Token": "tip-token",
        "content-type": "application/json",
    }

    tokens = extract_inbound_auth(headers)

    assert tokens.authorization_token == "user-token"
    assert tokens.authorization_scheme == "bearer"
    assert tokens.tip_token == "tip-token"
    assert redact_inbound_auth_headers(headers) == {"content-type": "application/json"}


@pytest.mark.parametrize("use_adk_extension", [False, True])
def test_a2a_request_saves_authorization_and_tip_headers(use_adk_extension):
    server = AgentkitAgentServerApp(
        agent=BaseAgent(name="a2a_inbound_auth_agent"),
        enable_auth=True,
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": "msg-1",
                "role": "user",
                "contextId": "ctx-1",
                "parts": [{"kind": "text", "text": "hello"}],
            }
        },
    }
    headers = {
        "Authorization": "Bearer user-token",
        "X-Ve-TIP-Token": "tip-token",
    }
    if use_adk_extension:
        headers[HTTP_EXTENSION_HEADER] = _NEW_A2A_ADK_INTEGRATION_EXTENSION

    with TestClient(server.app) as client:
        response = client.post(
            "/",
            json=payload,
            headers=headers,
        )

    assert response.status_code == 200
    auth_credential = asyncio.run(
        server.server.credential_service.get_credential(
            app_name="a2a_inbound_auth_agent",
            user_id="A2A_USER_ctx-1",
            credential_key=INBOUND_AUTH_CREDENTIAL_KEY,
        )
    )
    tip_credential = asyncio.run(
        server.server.credential_service.get_credential(
            app_name="a2a_inbound_auth_agent",
            user_id="A2A_USER_ctx-1",
            credential_key=TIP_TOKEN_CREDENTIAL_KEY,
        )
    )
    assert auth_credential.http.scheme == "bearer"
    assert auth_credential.http.credentials.token == "user-token"
    assert tip_credential.api_key == "tip-token"
