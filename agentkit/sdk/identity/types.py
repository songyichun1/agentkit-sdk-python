# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

# Request/response models for the InboundAuthConfig APIs.
#
# ``CreateInboundAuthConfig`` mirrors the published OpenAPI definition
# (Version 2025-10-30). ``ListInboundAuthConfigs`` uses the id service's
# PageNumber/PageSize pagination contract.

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class IdentityBaseModel(BaseModel):
    """AgentKit auto-generated base model"""

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# Data Types
class ApiKeyInfo(IdentityBaseModel):
    location: str = Field(..., alias="Location")
    parameter_name: Optional[str] = Field(default=None, alias="ParameterName")
    prefix: Optional[str] = Field(default=None, alias="Prefix")


# Backward-compatible name used by earlier SDK code.
ApiKeyMetadata = ApiKeyInfo


class ApiKeyAuthConfig(IdentityBaseModel):
    api_key_name: str = Field(..., alias="ApiKeyName")
    api_key: Optional[str] = Field(default=None, alias="ApiKey")
    api_key_metadata: Optional[list[ApiKeyInfo]] = Field(
        default=None, alias="ApiKeyMetadata"
    )
    expiry_timestamp: Optional[int] = Field(default=None, alias="ExpiryTimestamp")


class JwtAuthConfig(IdentityBaseModel):
    discovery_url: str = Field(..., alias="DiscoveryUrl")
    allowed_audiences: Optional[list[str]] = Field(
        default=None, alias="AllowedAudiences"
    )
    allowed_clients: Optional[list[str]] = Field(default=None, alias="AllowedClients")


class InboundAuthConfig(IdentityBaseModel):
    trn: str = Field(..., alias="Trn")
    inbound_auth_config_id: str = Field(..., alias="InboundAuthConfigId")
    config_name: str = Field(..., alias="ConfigName")
    description: Optional[str] = Field(default=None, alias="Description")
    auth_type: str = Field(..., alias="AuthType")
    jwt_auth_config: Optional[JwtAuthConfig] = Field(
        default=None, alias="JwtAuthConfig"
    )
    api_key_auth_configs: Optional[list[ApiKeyAuthConfig]] = Field(
        default=None, alias="ApiKeyAuthConfigs"
    )
    created_at: str = Field(..., alias="CreatedAt")
    updated_at: str = Field(..., alias="UpdatedAt")
    instance_id: Optional[str] = Field(default=None, alias="InstanceId")


# CreateInboundAuthConfig - Request
class CreateInboundAuthConfigRequest(IdentityBaseModel):
    config_name: Optional[str] = Field(default=None, alias="ConfigName")
    description: Optional[str] = Field(default=None, alias="Description")
    auth_type: str = Field(..., alias="AuthType")
    instance_id: Optional[str] = Field(default=None, alias="InstanceId")
    api_key_auth_configs: Optional[list[ApiKeyAuthConfig]] = Field(
        default=None, alias="ApiKeyAuthConfigs"
    )
    jwt_auth_config: Optional[JwtAuthConfig] = Field(
        default=None, alias="JwtAuthConfig"
    )


# CreateInboundAuthConfig - Response
class CreateInboundAuthConfigResponse(InboundAuthConfig):
    pass


# ListInboundAuthConfigs - Request
class ListInboundAuthConfigsRequest(IdentityBaseModel):
    page_number: int = Field(..., alias="PageNumber")
    page_size: int = Field(..., alias="PageSize")
    auth_type: Optional[str] = Field(default=None, alias="AuthType")
    instance_id: Optional[str] = Field(default=None, alias="InstanceId")


# ListInboundAuthConfigs - Response
class InboundAuthConfigForList(InboundAuthConfig):
    pass


class ListInboundAuthConfigsResponse(IdentityBaseModel):
    page_number: int = Field(..., alias="PageNumber")
    page_size: int = Field(..., alias="PageSize")
    total_count: int = Field(..., alias="TotalCount")
    inbound_auth_configs: Optional[list[InboundAuthConfigForList]] = Field(
        default=None, alias="InboundAuthConfigs"
    )


# DeleteInboundAuthConfig - Request
class DeleteInboundAuthConfigRequest(IdentityBaseModel):
    inbound_auth_config_id: str = Field(..., alias="InboundAuthConfigId")


# DeleteInboundAuthConfig - Response
class DeleteInboundAuthConfigResponse(IdentityBaseModel):
    pass
