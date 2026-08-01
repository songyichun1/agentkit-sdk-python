# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""HTTP transport that injects target-bound TIPs inside trusted SDK code."""

from __future__ import annotations

import http.cookiejar
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import requests

from agentkit.identity.errors import TargetNotConfiguredError, TargetRequestError
from agentkit.identity.runtime import RuntimeIdentity


class _RejectAllCookies(http.cookiejar.DefaultCookiePolicy):
    """Keep a protected-target transport bearer-only across all responses."""

    def set_ok(self, cookie: Any, request: Any) -> bool:
        return False

    def return_ok(self, cookie: Any, request: Any) -> bool:
        return False


_FORBIDDEN_HEADERS = {
    "authorization",
    "cookie",
    "forwarded",
    "host",
    "proxy-authorization",
    "x-original-url",
    "x-rewrite-url",
}
_FORBIDDEN_METHODS = {"CONNECT", "TRACE"}


class AuthorizedSession:
    """Call registered HTTPS targets without exposing their bearer token."""

    def __init__(
        self,
        identity: RuntimeIdentity,
    ) -> None:
        self._identity = identity
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.cookies = http.cookiejar.CookieJar(policy=_RejectAllCookies())

    def request(
        self,
        method: str,
        target_alias: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> requests.Response:
        normalized_method = method.strip().upper()
        if normalized_method in _FORBIDDEN_METHODS:
            raise ValueError("HTTP method is not allowed for protected targets")
        target = self._identity.target(target_alias)
        if target.base_url is None:
            raise TargetNotConfiguredError(
                "the protected target has no registered HTTP base URL"
            )
        parsed_path = urlsplit(path)
        if parsed_path.scheme or parsed_path.netloc:
            raise ValueError("authorized request path must be relative")
        decoded_path = parsed_path.path
        for _ in range(3):
            next_value = unquote(decoded_path)
            if next_value == decoded_path:
                break
            decoded_path = next_value
        if "\\" in decoded_path or any(
            segment in {".", ".."} for segment in decoded_path.split("/")
        ):
            raise ValueError("authorized request path cannot contain path traversal")
        request_headers = dict(headers or {})
        forbidden_headers = {
            key
            for key in request_headers
            if key.lower() in _FORBIDDEN_HEADERS
            or key.lower().startswith("x-forwarded-")
        }
        if forbidden_headers:
            raise ValueError(
                "security-sensitive headers are managed by AgentKit Identity"
            )
        forbidden_options = {
            "allow_redirects",
            "auth",
            "cert",
            "cookies",
            "hooks",
            "proxies",
            "verify",
        }.intersection(kwargs)
        if forbidden_options:
            raise ValueError(
                "security-sensitive request options are managed by AgentKit Identity"
            )
        workload_token = self._identity._token_for(target_alias)
        request_headers["Authorization"] = f"Bearer {workload_token.compact}"
        base_url = target.base_url.rstrip("/") + "/"
        url = urljoin(base_url, path.lstrip("/"))
        if not url.startswith(base_url):
            raise ValueError("authorized request path escaped its registered target")
        response = self._send(
            normalized_method,
            url,
            headers=request_headers,
            timeout=timeout,
            kwargs=kwargs,
        )
        if response is None:
            # Remove bearer-bearing locals before creating a traceback visible
            # to Agent or Tool code. _send converts requests failures to a
            # sentinel, so its private frame is not part of this traceback.
            request_headers.pop("Authorization", None)
            workload_token = None
            raise TargetRequestError("protected target request failed") from None
        return response

    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        kwargs: dict[str, Any],
    ) -> requests.Response | None:
        """Contain requests objects that may retain the injected TIP."""

        try:
            response = self._session.request(
                method,
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
                **kwargs,
            )
        except requests.RequestException:
            return None
        if not isinstance(response, requests.Response):
            return None
        # requests.Response otherwise exposes the PreparedRequest (and TIP) as
        # response.request. It is not needed for status/body/streaming APIs.
        response.request = None
        return response
