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

from typing import Any

from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.credential_service.base_credential_service import (
    BaseCredentialService,
)


class AgentkitCredentialService(BaseCredentialService):
    """AgentKit-owned ADK credential service with a direct write API."""

    def __init__(self) -> None:
        super().__init__()
        self._credentials: dict[str, dict[str, dict[str, AuthCredential]]] = {}

    async def load_credential(
        self,
        auth_config: Any,
        callback_context: Any,
    ) -> AuthCredential | None:
        app_name, user_id = self._resolve_context(callback_context)
        credential_key = self._resolve_credential_key(auth_config)
        if credential_key is None:
            return None
        return await self.get_credential(
            app_name=app_name,
            user_id=user_id,
            credential_key=credential_key,
        )

    async def save_credential(
        self,
        auth_config: Any,
        callback_context: Any,
    ) -> None:
        app_name, user_id = self._resolve_context(callback_context)
        credential_key = self._resolve_credential_key(auth_config)
        credential = getattr(auth_config, "exchanged_auth_credential", None)
        if credential_key and credential is not None:
            await self.set_credential(
                app_name=app_name,
                user_id=user_id,
                credential_key=credential_key,
                credential=credential,
            )

    async def set_credential(
        self,
        app_name: str,
        user_id: str,
        credential_key: str,
        credential: AuthCredential,
    ) -> None:
        self._credentials.setdefault(app_name, {})
        self._credentials[app_name].setdefault(user_id, {})
        self._credentials[app_name][user_id][credential_key] = credential

    async def get_credential(
        self,
        app_name: str,
        user_id: str,
        credential_key: str,
    ) -> AuthCredential | None:
        return self._credentials.get(app_name, {}).get(user_id, {}).get(credential_key)

    def _resolve_context(self, callback_context: Any) -> tuple[str, str]:
        invocation_context = getattr(callback_context, "_invocation_context", None)
        if invocation_context is None:
            invocation_context = getattr(callback_context, "invocation_context", None)
        return invocation_context.app_name, invocation_context.user_id

    def _resolve_credential_key(self, auth_config: Any) -> str | None:
        credential_key = getattr(auth_config, "credential_key", None)
        if credential_key is None and hasattr(auth_config, "get_credential_key"):
            credential_key = auth_config.get_credential_key()
        return credential_key
