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

"""Compatibility imports for AgentServer inbound-auth helpers."""

from agentkit.apps.agent_server_app.inbound_auth_adapter import (
    inbound_tokens_to_adk_credentials,
    save_inbound_auth,
)
from agentkit.apps.auth.inbound import (
    AUTHORIZATION_HEADER,
    INBOUND_AUTH_CREDENTIAL_KEY,
    TIP_TOKEN_CREDENTIAL_KEY,
    TIP_TOKEN_HEADER,
    InboundAuthTokens,
    extract_inbound_auth,
    redact_inbound_auth_headers,
    strip_bearer,
)

__all__ = [
    "AUTHORIZATION_HEADER",
    "INBOUND_AUTH_CREDENTIAL_KEY",
    "TIP_TOKEN_CREDENTIAL_KEY",
    "TIP_TOKEN_HEADER",
    "InboundAuthTokens",
    "extract_inbound_auth",
    "inbound_tokens_to_adk_credentials",
    "redact_inbound_auth_headers",
    "save_inbound_auth",
    "strip_bearer",
]
