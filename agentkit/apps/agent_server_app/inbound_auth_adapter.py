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

import logging
from types import SimpleNamespace
from typing import Any

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig, ExecuteInterceptor
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
)

from agentkit.apps.auth.inbound import (
    INBOUND_AUTH_CREDENTIAL_KEY,
    TIP_TOKEN_CREDENTIAL_KEY,
    InboundAuthTokens,
    extract_inbound_auth,
)

logger = logging.getLogger(__name__)
INBOUND_AUTH_TOKENS_SCOPE_KEY = "agentkit.inbound_auth_tokens"


class InboundAuthCaptureMiddleware:
    """Capture inbound auth before identity middleware scrubs Authorization."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            tokens = extract_inbound_auth(headers)
            if tokens:
                scope = dict(scope)
                scope[INBOUND_AUTH_TOKENS_SCOPE_KEY] = tokens
        await self.app(scope, receive, send)


def inbound_tokens_to_adk_credentials(
    tokens: InboundAuthTokens,
) -> dict[str, AuthCredential]:
    credentials: dict[str, AuthCredential] = {}
    if tokens.authorization_token:
        credentials[INBOUND_AUTH_CREDENTIAL_KEY] = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme=tokens.authorization_scheme or "header",
                credentials=HttpCredentials(token=tokens.authorization_token),
            ),
        )
    if tokens.tip_token:
        credentials[TIP_TOKEN_CREDENTIAL_KEY] = AuthCredential(
            auth_type=AuthCredentialTypes.API_KEY,
            api_key=tokens.tip_token,
        )
    return credentials


def _request_inbound_auth_tokens(request: Any) -> InboundAuthTokens:
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        captured = scope.get(INBOUND_AUTH_TOKENS_SCOPE_KEY)
        if isinstance(captured, InboundAuthTokens):
            return captured
    return extract_inbound_auth(request.headers)


async def save_inbound_auth(
    *,
    request: Any,
    app_name: str,
    user_id: str,
    credential_service: Any,
) -> None:
    try:
        set_credential = getattr(credential_service, "set_credential", None)
        if not callable(set_credential):
            logger.warning("Credential service cannot store inbound auth credentials")
            return

        tokens = _request_inbound_auth_tokens(request)
        for credential_key, credential in inbound_tokens_to_adk_credentials(
            tokens
        ).items():
            await set_credential(
                app_name=app_name,
                user_id=user_id,
                credential_key=credential_key,
                credential=credential,
            )
    except Exception:
        logger.warning("Failed to save inbound auth credentials", exc_info=True)


def _resolve_a2a_user_id(context: Any) -> str:
    call_context = getattr(context, "call_context", None)
    user = getattr(call_context, "user", None)
    user_name = getattr(user, "user_name", None)
    if user_name:
        return user_name

    context_id = getattr(context, "context_id", None)
    return f"A2A_USER_{context_id}"


def _ensure_a2a_runner_credential_service(
    runner: Any,
    credential_service: Any,
) -> Any:
    runner_credential_service = getattr(runner, "credential_service", None)
    if runner_credential_service is not None:
        return runner_credential_service

    try:
        runner.credential_service = credential_service
    except Exception:
        return credential_service
    return getattr(runner, "credential_service", None) or credential_service


def _build_a2a_inbound_auth_interceptor(
    *,
    app_name: str,
    credential_service: Any,
) -> ExecuteInterceptor:
    async def before_agent(context: Any) -> Any:
        call_context = getattr(context, "call_context", None)
        state = getattr(call_context, "state", {}) if call_context else {}
        headers = state.get("headers", {}) if isinstance(state, dict) else {}
        if not headers:
            return context

        await save_inbound_auth(
            request=SimpleNamespace(headers=headers, scope={}),
            app_name=app_name,
            user_id=_resolve_a2a_user_id(context),
            credential_service=credential_service,
        )
        return context

    return ExecuteInterceptor(before_agent=before_agent)


def build_a2a_inbound_auth_executor_factory(
    *,
    runner: Any,
    app_name: str,
    credential_service: Any,
) -> Any:
    a2a_credential_service = _ensure_a2a_runner_credential_service(
        runner,
        credential_service,
    )
    a2a_config = A2aAgentExecutorConfig(
        execute_interceptors=[
            _build_a2a_inbound_auth_interceptor(
                app_name=app_name,
                credential_service=a2a_credential_service,
            )
        ]
    )

    def a2a_agent_executor_factory(runner: Any) -> A2aAgentExecutor:
        return A2aAgentExecutor(runner=runner, config=a2a_config)

    return a2a_agent_executor_factory
