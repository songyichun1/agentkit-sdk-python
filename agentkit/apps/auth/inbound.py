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

from dataclasses import dataclass
from typing import Any

INBOUND_AUTH_CREDENTIAL_KEY = "inbound_auth"
TIP_TOKEN_CREDENTIAL_KEY = "ve_tip_token"
AUTHORIZATION_HEADER = "Authorization"
TIP_TOKEN_HEADER = "X-Ve-TIP-Token"


@dataclass(frozen=True, repr=False)
class InboundAuthTokens:
    authorization_token: str | None = None
    authorization_scheme: str | None = None
    tip_token: str | None = None

    def __bool__(self) -> bool:
        return bool(self.authorization_token or self.tip_token)


def strip_bearer(value: str) -> tuple[str, bool]:
    value = (value or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip(), True
    return value, False


def _get_header(headers: Any, name: str) -> str | None:
    expected = name.lower()
    if hasattr(headers, "items"):
        for key, value in headers.items():
            if isinstance(key, bytes):
                key_text = key.decode("latin-1")
            else:
                key_text = str(key)
            if key_text.lower() == expected:
                return value
    return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())


def extract_inbound_auth(
    headers: Any,
) -> InboundAuthTokens:
    authorization_token = None
    authorization_scheme = None
    tip_token = None

    auth_header = _get_header(headers, AUTHORIZATION_HEADER)
    if auth_header:
        token, has_bearer = strip_bearer(auth_header)
        if token:
            authorization_token = token
            authorization_scheme = "bearer" if has_bearer else "header"

    raw_tip_token = _get_header(headers, TIP_TOKEN_HEADER)
    if raw_tip_token and raw_tip_token.strip():
        tip_token = raw_tip_token.strip()

    return InboundAuthTokens(
        authorization_token=authorization_token,
        authorization_scheme=authorization_scheme,
        tip_token=tip_token,
    )


def redact_inbound_auth_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive_names = {
        AUTHORIZATION_HEADER.lower(),
        "token",
        TIP_TOKEN_HEADER.lower(),
    }
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in sensitive_names
    }
