# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""HTTP transport that injects target-bound TIPs inside trusted SDK code."""

from __future__ import annotations

import http.cookiejar
import math
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
    "connection",
    "content-length",
    "cookie",
    "forwarded",
    "host",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
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
        for _ in range(10):
            next_value = unquote(decoded_path)
            if next_value == decoded_path:
                break
            decoded_path = next_value
        else:
            raise ValueError("authorized request path has excessive encoding")
        if unquote(decoded_path) != decoded_path:
            raise ValueError("authorized request path has unstable encoding")
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
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError(
                "protected target timeout must be a positive finite number"
            )
        base_url = target.base_url.rstrip("/") + "/"
        url = urljoin(base_url, path.lstrip("/"))
        parsed_base = urlsplit(base_url)
        parsed_url = urlsplit(url)
        base_origin = (
            parsed_base.scheme,
            parsed_base.hostname,
            parsed_base.port or 443,
        )
        request_origin = (
            parsed_url.scheme,
            parsed_url.hostname,
            parsed_url.port or 443,
        )
        base_path = parsed_base.path.rstrip("/")
        request_path = parsed_url.path
        if request_origin != base_origin or not (
            request_path == base_path or request_path.startswith(base_path + "/")
        ):
            raise ValueError("authorized request path escaped its registered target")
        lease = self._identity._request_lease()
        with lease.use():
            response = self._request_with_credential(
                normalized_method,
                target_alias,
                url,
                headers=request_headers,
                timeout=float(timeout),
                kwargs=kwargs,
            )
        if response is None:
            raise TargetRequestError("protected target request failed") from None
        return response

    def _request_with_credential(
        self,
        method: str,
        target_alias: str,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        kwargs: dict[str, Any],
    ) -> requests.Response | None:
        """Contain every frame that can retain an injected workload TIP."""

        workload_token = None
        try:
            workload_token = self._identity._token_for(target_alias)
            headers["Authorization"] = f"Bearer {workload_token.compact}"
            return self._send(
                method,
                url,
                headers=headers,
                timeout=timeout,
                kwargs=kwargs,
            )
        except Exception:  # noqa: BLE001 - collapse secret-bearing failures
            return None
        finally:
            headers.pop("Authorization", None)
            workload_token = None

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
            if not isinstance(response, requests.Response):
                return None
            # requests.Response otherwise exposes the PreparedRequest (and TIP) as
            # response.request. It is not needed for status/body/streaming APIs.
            response.request = None
            return response
        except Exception:  # noqa: BLE001 - discard all bearer-bearing frames
            return None
