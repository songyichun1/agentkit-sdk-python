# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""OIDC discovery and cryptographic ID Token verification."""

from __future__ import annotations

import hmac
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

import jwt

from agentkit.identity.errors import (
    IdentityAuthenticationError,
    IdentityUnavailableError,
)
from agentkit.identity.types import VerifiedUserIdentity

_MAX_DISCOVERY_BYTES = 1024 * 1024
_MAX_JWKS_BYTES = 4 * 1024 * 1024
_ASYMMETRIC_JWT_ALGORITHMS = frozenset(
    {
        "EdDSA",
        "ES256",
        "ES384",
        "ES512",
        "PS256",
        "PS384",
        "PS512",
        "RS256",
        "RS384",
        "RS512",
    }
)


def _integral_numeric_date(value: Any) -> int | None:
    """Normalize an RFC 7519 NumericDate without broadening time semantics."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _is_loopback(hostname: str | None) -> bool:
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _validate_remote_url(
    url: str,
    *,
    label: str,
    allow_insecure_loopback: bool = False,
) -> str:
    parsed = urllib.parse.urlsplit(url)
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} contains an invalid port") from exc
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an absolute URL without credentials")
    if parsed.scheme != "https" and not (
        allow_insecure_loopback
        and parsed.scheme == "http"
        and _is_loopback(parsed.hostname)
    ):
        raise ValueError(f"{label} must use HTTPS")
    if parsed.fragment:
        raise ValueError(f"{label} cannot contain a fragment")
    return url


def _as_discovery_url(value: str, *, allow_insecure_loopback: bool = False) -> str:
    value = _validate_remote_url(
        value,
        label="OIDC discovery URL",
        allow_insecure_loopback=allow_insecure_loopback,
    )
    if "/.well-known/" in urllib.parse.urlsplit(value).path:
        return value
    return value.rstrip("/") + "/.well-known/openid-configuration"


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, str(parsed.hostname).lower(), port


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(
        self,
        origin: tuple[str, str, int],
        *,
        allow_insecure_loopback: bool = False,
    ) -> None:
        super().__init__()
        self._origin = origin
        self._allow_insecure_loopback = allow_insecure_loopback

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _validate_remote_url(
                newurl,
                label="redirect URL",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
        except ValueError as exc:
            raise urllib.error.HTTPError(
                newurl, 403, "unsafe redirect denied", headers, fp
            ) from exc
        if _origin(newurl) != self._origin:
            raise urllib.error.HTTPError(
                newurl, 403, "cross-origin redirect denied", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_json_document(
    url: str,
    *,
    timeout_seconds: float,
    max_bytes: int,
    label: str,
    allow_insecure_loopback: bool = False,
) -> dict[str, Any]:
    _validate_remote_url(
        url,
        label=label,
        allow_insecure_loopback=allow_insecure_loopback,
    )
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(
        _SameOriginRedirectHandler(
            _origin(url),
            allow_insecure_loopback=allow_insecure_loopback,
        )
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            final_url = _validate_remote_url(
                response.geturl(),
                label=f"{label} response URL",
                allow_insecure_loopback=allow_insecure_loopback,
            )
            if _origin(final_url) != _origin(url):
                raise ValueError(f"{label} redirected across origins")
            raw = response.read(max_bytes + 1)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise IdentityUnavailableError(f"{label} is unavailable") from exc
    if len(raw) > max_bytes:
        raise IdentityUnavailableError(f"{label} response is too large")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityUnavailableError(f"{label} returned invalid JSON") from exc
    if not isinstance(document, dict):
        raise IdentityUnavailableError(f"{label} returned an invalid object")
    return document


class _PinnedPyJWKClient(jwt.PyJWKClient):
    def __init__(
        self,
        *args: Any,
        allow_insecure_loopback: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._allow_insecure_loopback = allow_insecure_loopback

    def fetch_data(self) -> Any:
        try:
            jwk_set = _read_json_document(
                self.uri,
                timeout_seconds=self.timeout,
                max_bytes=_MAX_JWKS_BYTES,
                label="OIDC signing keys",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
        except IdentityUnavailableError as exc:
            raise jwt.PyJWKClientConnectionError(
                "OIDC signing keys are unavailable"
            ) from exc
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(jwk_set)
        return jwk_set


class OidcJwtVerifier:
    """Verify ID Tokens against one deployment-controlled OIDC configuration."""

    def __init__(
        self,
        *,
        discovery_url: str,
        expected_issuer: str,
        allowed_clients: tuple[str, ...],
        allowed_algorithms: tuple[str, ...] = ("RS256",),
        clock_skew_seconds: int = 30,
        timeout_seconds: float = 5.0,
        allowed_jwks_origins: tuple[str, ...] = (),
        allow_insecure_loopback: bool = False,
        jwks_cache_seconds: int = 300,
        discovery_document: Mapping[str, Any] | None = None,
        signing_key_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        if not allowed_clients:
            raise ValueError("at least one allowed OIDC client is required")
        if not allowed_algorithms:
            raise ValueError("at least one allowed JWT algorithm is required")
        if not set(allowed_algorithms).issubset(_ASYMMETRIC_JWT_ALGORITHMS):
            raise ValueError("ID Tokens must use approved asymmetric algorithms")
        if not 1 <= jwks_cache_seconds <= 3600:
            raise ValueError("jwks_cache_seconds must be between 1 and 3600")
        self._allow_insecure_loopback = allow_insecure_loopback
        self.discovery_url = _as_discovery_url(
            discovery_url,
            allow_insecure_loopback=allow_insecure_loopback,
        )
        self.allowed_clients = tuple(allowed_clients)
        self.allowed_algorithms = tuple(allowed_algorithms)
        self.expected_issuer = _validate_remote_url(
            expected_issuer,
            label="expected OIDC issuer",
            allow_insecure_loopback=allow_insecure_loopback,
        )
        self.clock_skew_seconds = clock_skew_seconds
        self.timeout_seconds = timeout_seconds
        self.jwks_cache_seconds = jwks_cache_seconds
        self._allowed_jwks_origins = frozenset(
            _origin(
                _validate_remote_url(
                    url,
                    label="allowed JWKS origin",
                    allow_insecure_loopback=allow_insecure_loopback,
                )
            )
            for url in allowed_jwks_origins
        )
        self._discovery = dict(discovery_document or {})
        self._signing_key_resolver = signing_key_resolver
        self._jwk_client: jwt.PyJWKClient | None = None

    def _load_discovery(self) -> dict[str, Any]:
        if self._discovery:
            return self._discovery
        document = _read_json_document(
            self.discovery_url,
            timeout_seconds=self.timeout_seconds,
            max_bytes=_MAX_DISCOVERY_BYTES,
            label="OIDC discovery",
            allow_insecure_loopback=self._allow_insecure_loopback,
        )
        self._discovery = document
        return self._discovery

    def _metadata(self) -> tuple[str, str]:
        document = self._load_discovery()
        issuer = str(document.get("issuer") or "")
        jwks_uri = str(document.get("jwks_uri") or "")
        try:
            _validate_remote_url(
                issuer,
                label="OIDC issuer",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
            _validate_remote_url(
                jwks_uri,
                label="OIDC JWKS URL",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
        except ValueError as exc:
            raise IdentityUnavailableError(
                "OIDC discovery is missing trusted issuer metadata"
            ) from exc
        if issuer != self.expected_issuer:
            raise IdentityUnavailableError(
                "OIDC discovery issuer does not match the configured trust anchor"
            )
        allowed_origins = {
            _origin(self.discovery_url),
            *self._allowed_jwks_origins,
        }
        if _origin(jwks_uri) not in allowed_origins:
            raise IdentityUnavailableError("OIDC JWKS URL is not on a trusted origin")
        # OIDC issuer comparison is exact; a trailing slash is significant and
        # must not be normalized away after discovery.
        return issuer, jwks_uri

    def _resolve_signing_key(self, compact: str, jwks_uri: str) -> Any:
        if self._signing_key_resolver is not None:
            return self._signing_key_resolver(compact)
        if self._jwk_client is None:
            self._jwk_client = _PinnedPyJWKClient(
                jwks_uri,
                cache_keys=False,
                lifespan=self.jwks_cache_seconds,
                timeout=self.timeout_seconds,
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
        try:
            return self._jwk_client.get_signing_key_from_jwt(compact).key
        except jwt.PyJWKClientConnectionError as exc:
            raise IdentityUnavailableError("OIDC signing keys are unavailable") from exc
        except Exception as exc:  # PyJWT has several key/JWKS exception types.
            raise IdentityAuthenticationError(
                "the inbound ID Token has no trusted signing key"
            ) from exc

    def verify(
        self,
        compact: str,
        *,
        nonce: str | None = None,
        expected_subject: str | None = None,
    ) -> VerifiedUserIdentity:
        """Verify signature and OIDC identity claims, then return safe metadata."""

        if not compact or compact.count(".") != 2:
            raise IdentityAuthenticationError("a valid Bearer ID Token is required")
        try:
            header = jwt.get_unverified_header(compact)
        except jwt.PyJWTError as exc:
            raise IdentityAuthenticationError(
                "the inbound ID Token is malformed"
            ) from exc
        algorithm = header.get("alg")
        if algorithm not in self.allowed_algorithms:
            raise IdentityAuthenticationError(
                "the inbound ID Token uses an unsupported signing algorithm"
            )

        issuer, jwks_uri = self._metadata()
        signing_key = self._resolve_signing_key(compact, jwks_uri)
        try:
            claims = jwt.decode(
                compact,
                signing_key,
                algorithms=list(self.allowed_algorithms),
                audience=list(self.allowed_clients),
                issuer=issuer,
                leeway=self.clock_skew_seconds,
                options={"require": ["sub", "iss", "aud", "exp", "iat"]},
            )
        except (jwt.PyJWTError, TypeError, ValueError, OverflowError) as exc:
            raise IdentityAuthenticationError(
                "the inbound ID Token failed verification"
            ) from exc

        subject = claims.get("sub")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(subject, str) or not subject:
            raise IdentityAuthenticationError("the inbound ID Token has no subject")
        if not isinstance(issued_at, int) or not isinstance(expires_at, int):
            raise IdentityAuthenticationError(
                "the inbound ID Token has invalid time claims"
            )
        if expires_at <= issued_at:
            raise IdentityAuthenticationError(
                "the inbound ID Token has an invalid lifetime"
            )
        if expected_subject is not None and subject != expected_subject:
            raise IdentityAuthenticationError(
                "the refreshed ID Token changed the authenticated subject"
            )

        raw_audiences = claims.get("aud")
        if isinstance(raw_audiences, str):
            audiences = (raw_audiences,)
        elif isinstance(raw_audiences, list) and all(
            isinstance(value, str) for value in raw_audiences
        ):
            audiences = tuple(raw_audiences)
        else:
            raise IdentityAuthenticationError(
                "the inbound ID Token has an invalid audience"
            )

        authorized_party = claims.get("azp")
        if len(audiences) > 1 and not isinstance(authorized_party, str):
            raise IdentityAuthenticationError(
                "a multi-audience ID Token must identify its authorized party"
            )
        if isinstance(authorized_party, str) and authorized_party not in audiences:
            raise IdentityAuthenticationError(
                "the inbound ID Token authorized party is not an audience"
            )
        client_id = (
            authorized_party
            if isinstance(authorized_party, str)
            else next(
                (aud for aud in audiences if aud in self.allowed_clients),
                "",
            )
        )
        if client_id not in self.allowed_clients:
            raise IdentityAuthenticationError(
                "the inbound ID Token client is not allowed"
            )

        token_nonce = claims.get("nonce")
        if nonce is not None and (
            not isinstance(token_nonce, str)
            or not hmac.compare_digest(token_nonce, nonce)
        ):
            raise IdentityAuthenticationError("the ID Token nonce does not match")

        return VerifiedUserIdentity(
            subject=subject,
            issuer=issuer,
            audiences=audiences,
            client_id=client_id,
            expires_at=expires_at,
            issued_at=issued_at,
            claims=claims,
        )


class WorkloadJwtVerifier:
    """Verify an Agent Identity workload/TIP JWT for one trusted pool issuer."""

    def __init__(
        self,
        *,
        discovery_url: str,
        expected_issuer: str,
        allowed_algorithms: tuple[str, ...] = ("RS256",),
        clock_skew_seconds: int = 30,
        timeout_seconds: float = 5.0,
        allowed_jwks_origins: tuple[str, ...] = (),
        allow_insecure_loopback: bool = False,
        jwks_cache_seconds: int = 300,
        discovery_document: Mapping[str, Any] | None = None,
        signing_key_resolver: Callable[[str], Any] | None = None,
    ) -> None:
        if not allowed_algorithms:
            raise ValueError("at least one JWT algorithm is required")
        if not set(allowed_algorithms).issubset(_ASYMMETRIC_JWT_ALGORITHMS):
            raise ValueError("workload tokens must use approved asymmetric algorithms")
        if not 1 <= jwks_cache_seconds <= 3600:
            raise ValueError("jwks_cache_seconds must be between 1 and 3600")
        self._allow_insecure_loopback = allow_insecure_loopback
        self.discovery_url = _as_discovery_url(
            discovery_url,
            allow_insecure_loopback=allow_insecure_loopback,
        )
        self.allowed_algorithms = tuple(allowed_algorithms)
        self.expected_issuer = _validate_remote_url(
            expected_issuer,
            label="expected workload token issuer",
            allow_insecure_loopback=allow_insecure_loopback,
        )
        self.clock_skew_seconds = clock_skew_seconds
        self.timeout_seconds = timeout_seconds
        self.jwks_cache_seconds = jwks_cache_seconds
        self._allowed_jwks_origins = frozenset(
            _origin(
                _validate_remote_url(
                    url,
                    label="allowed workload JWKS origin",
                    allow_insecure_loopback=allow_insecure_loopback,
                )
            )
            for url in allowed_jwks_origins
        )
        self._discovery = dict(discovery_document or {})
        self._signing_key_resolver = signing_key_resolver
        self._jwk_client: jwt.PyJWKClient | None = None

    def _metadata(self) -> tuple[str, str]:
        document = self._discovery
        if not document:
            document = _read_json_document(
                self.discovery_url,
                timeout_seconds=self.timeout_seconds,
                max_bytes=_MAX_DISCOVERY_BYTES,
                label="workload OIDC discovery",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
            self._discovery = document
        issuer = str(document.get("issuer") or "")
        jwks_uri = str(document.get("jwks_uri") or "")
        try:
            _validate_remote_url(
                issuer,
                label="workload token issuer",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
            _validate_remote_url(
                jwks_uri,
                label="workload token JWKS URL",
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
        except ValueError as exc:
            raise IdentityUnavailableError(
                "workload OIDC discovery is missing trusted issuer metadata"
            ) from exc
        if issuer != self.expected_issuer:
            raise IdentityUnavailableError(
                "workload discovery issuer does not match the configured trust anchor"
            )
        allowed_origins = {_origin(self.discovery_url), *self._allowed_jwks_origins}
        if _origin(jwks_uri) not in allowed_origins:
            raise IdentityUnavailableError(
                "workload token JWKS URL is not on a trusted origin"
            )
        return issuer, jwks_uri

    def _resolve_signing_key(self, compact: str, jwks_uri: str) -> Any:
        if self._signing_key_resolver is not None:
            return self._signing_key_resolver(compact)
        if self._jwk_client is None:
            self._jwk_client = _PinnedPyJWKClient(
                jwks_uri,
                cache_keys=False,
                lifespan=self.jwks_cache_seconds,
                timeout=self.timeout_seconds,
                allow_insecure_loopback=self._allow_insecure_loopback,
            )
        try:
            return self._jwk_client.get_signing_key_from_jwt(compact).key
        except jwt.PyJWKClientConnectionError as exc:
            raise IdentityUnavailableError(
                "workload token signing keys are unavailable"
            ) from exc
        except Exception as exc:
            raise IdentityAuthenticationError(
                "the workload token has no trusted signing key"
            ) from exc

    def verify(self, compact: str, *, audience: str) -> dict[str, Any]:
        """Verify signature, issuer, audience, lifetime, and required claims."""

        if not compact or compact.count(".") != 2:
            raise IdentityAuthenticationError("the workload token is malformed")
        try:
            header = jwt.get_unverified_header(compact)
        except jwt.PyJWTError as exc:
            raise IdentityAuthenticationError(
                "the workload token is malformed"
            ) from exc
        if header.get("alg") not in self.allowed_algorithms:
            raise IdentityAuthenticationError(
                "the workload token uses an unsupported signing algorithm"
            )
        issuer, jwks_uri = self._metadata()
        signing_key = self._resolve_signing_key(compact, jwks_uri)
        try:
            claims = jwt.decode(
                compact,
                signing_key,
                algorithms=list(self.allowed_algorithms),
                audience=audience,
                issuer=issuer,
                leeway=self.clock_skew_seconds,
                options={"require": ["sub", "iss", "aud", "exp", "iat", "act"]},
            )
        except (jwt.PyJWTError, TypeError, ValueError, OverflowError) as exc:
            raise IdentityAuthenticationError(
                "the workload token failed verification"
            ) from exc
        issued_at = _integral_numeric_date(claims.get("iat"))
        expires_at = _integral_numeric_date(claims.get("exp"))
        if issued_at is None or expires_at is None or expires_at <= issued_at:
            raise IdentityAuthenticationError(
                "the workload token has an invalid lifetime"
            )
        claims["iat"] = issued_at
        claims["exp"] = expires_at
        return claims
