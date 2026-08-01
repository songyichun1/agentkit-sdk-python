# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Identity OpenAPI client for AgentKit Runtime Workload/OBO tokens."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from agentkit.client.base_service_client import ApiConfig, BaseServiceClient
from agentkit.identity.errors import TokenExchangeError, WorkloadBindingError
from agentkit.platform.configuration import Credentials, VolcConfiguration


class _ForJwtRequest(BaseModel):
    workload_pool_name: str = Field(alias="WorkloadPoolName")
    name: str = Field(alias="Name")
    user_token: str = Field(alias="UserToken", repr=False)
    audience: list[str] = Field(alias="Audience")
    duration_seconds: int = Field(alias="DurationSeconds")

    model_config = {"populate_by_name": True}


class _WorkloadTokenResponse(BaseModel):
    workload_access_token: str = Field(alias="WorkloadAccessToken", repr=False)
    expires_at: Any = Field(default=None, alias="ExpiresAt")

    model_config = {"populate_by_name": True}


class _AgentIdentityService(BaseServiceClient):
    API_ACTIONS: ClassVar[dict[str, ApiConfig]] = {
        "GetWorkloadAccessTokenForJWT": ApiConfig(
            action="GetWorkloadAccessTokenForJWT", method="POST"
        )
    }

    def __init__(self, *, credentials: Credentials, region: str) -> None:
        super().__init__(
            service="agent_identity",
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            session_token=credentials.session_token or "",
            region=region,
            service_name="agent-identity",
        )
        expected_host = f"id.{region}.volcengineapi.com"
        if (
            self.scheme != "https"
            or self.host.lower() != expected_host.lower()
            or self.service != "id"
            or self.api_version != "2025-10-30"
        ):
            raise WorkloadBindingError(
                "Agent Identity endpoint metadata cannot be overridden"
            )


def _runtime_credentials(region: str) -> Credentials:
    credentials = VolcConfiguration(region=region).get_vefaas_iam_credentials()
    if credentials is None:
        raise WorkloadBindingError("AgentKit Runtime IAM credentials are unavailable")
    return credentials


class IdentityClient:
    """Call Agent Identity with fresh Runtime IAM credentials per exchange."""

    def __init__(
        self,
        *,
        region: str = "cn-beijing",
        credential_provider: Callable[[], Credentials] | None = None,
        service_factory: Callable[[Credentials, str], Any] | None = None,
    ) -> None:
        self.region = region
        self._credential_provider = credential_provider or (
            lambda: _runtime_credentials(region)
        )
        self._service_factory = service_factory or (
            lambda credentials, service_region: _AgentIdentityService(
                credentials=credentials, region=service_region
            )
        )

    def exchange_for_jwt(
        self,
        *,
        workload_pool: str,
        workload_id: str,
        subject_token: str,
        audience: str,
        duration_seconds: int,
    ) -> tuple[str, Any]:
        """Mint one user-plus-Agent TIP without exposing server error bodies."""

        if not workload_pool or not workload_id or not subject_token or not audience:
            raise TokenExchangeError("the OBO request is incomplete")
        try:
            credentials = self._credential_provider()
            service = self._service_factory(credentials, self.region)
            result = service._invoke_api(
                "GetWorkloadAccessTokenForJWT",
                _ForJwtRequest(
                    WorkloadPoolName=workload_pool,
                    Name=workload_id,
                    UserToken=subject_token,
                    Audience=[audience],
                    DurationSeconds=duration_seconds,
                ),
                _WorkloadTokenResponse,
            )
        except (TokenExchangeError, WorkloadBindingError):
            raise
        except Exception:  # noqa: BLE001 - upstream errors may retain UserToken
            # Generated/OpenAPI exceptions may include request bodies.  Do not
            # chain or reproduce them because the request contains the ID Token.
            raise TokenExchangeError(
                "Identity could not mint a workload access token"
            ) from None
        token = result.workload_access_token
        if not isinstance(token, str) or not token:
            raise TokenExchangeError("Identity returned no workload access token")
        return token, result.expires_at
