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

# Auto-generated from API JSON definition
# Do not edit manually

from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, BaseModel, Field


class ModelGatewayBaseModel(BaseModel):
    """AgentKit auto-generated base model"""

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# Data Types
class ApiKeysForModelGateway(ModelGatewayBaseModel):
    name: Optional[str] = Field(default=None, alias="Name")
    value: Optional[str] = Field(default=None, alias="Value")


class AuthzConfigForModelGateway(ModelGatewayBaseModel):
    allow_all_providers: Optional[bool] = Field(default=None, alias="AllowAllProviders")
    provider_authz_configs: Optional[list[ProviderAuthzConfigsForModelGateway]] = Field(
        default=None, alias="ProviderAuthzConfigs"
    )


class ConsumerForCreateModelGateway(ModelGatewayBaseModel):
    consumer_name: str = Field(..., alias="ConsumerName")


class ConsumersForModelGateway(ModelGatewayBaseModel):
    consumer_id: Optional[str] = Field(default=None, alias="ConsumerId")
    consumer_name: Optional[str] = Field(default=None, alias="ConsumerName")
    model_gateway_id: Optional[str] = Field(default=None, alias="ModelGatewayId")
    api_keys: Optional[list[str]] = Field(default=None, alias="ApiKeys")
    authz_config: Optional[AuthzConfigForModelGateway] = Field(
        default=None, alias="AuthzConfig"
    )
    token_rate_limit_config: Optional[TokenRateLimitConfigForModelGateway] = Field(
        default=None, alias="TokenRateLimitConfig"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")
    tags: Optional[list[TagsForModelGateway]] = Field(default=None, alias="Tags")
    created_at: Optional[str] = Field(default=None, alias="CreatedAt")
    updated_at: Optional[str] = Field(default=None, alias="UpdatedAt")


class CredentialsForModelGateway(ModelGatewayBaseModel):
    type: Optional[str] = Field(default=None, alias="Type")
    api_keys: Optional[list[ApiKeysForModelGateway]] = Field(
        default=None, alias="ApiKeys"
    )


class ModelGatewaysForModelGateway(ModelGatewayBaseModel):
    model_gateway_id: Optional[str] = Field(default=None, alias="ModelGatewayId")
    retry_policy: Optional[RetryPolicyForModelGateway] = Field(
        default=None, alias="RetryPolicy"
    )
    project_name: Optional[str] = Field(default=None, alias="ProjectName")
    comments: Optional[str] = Field(default=None, alias="Comments")
    tags: Optional[list[TagsForModelGateway]] = Field(default=None, alias="Tags")
    status: Optional[str] = Field(default=None, alias="Status")
    message: Optional[str] = Field(default=None, alias="Message")
    created_at: Optional[str] = Field(default=None, alias="CreatedAt")
    updated_at: Optional[str] = Field(default=None, alias="UpdatedAt")


class ProviderAuthzConfigsForModelGateway(ModelGatewayBaseModel):
    provider_id: Optional[str] = Field(default=None, alias="ProviderId")
    allow_all_provider_models: Optional[bool] = Field(
        default=None, alias="AllowAllProviderModels"
    )
    allowed_provider_model_ids: Optional[list[str]] = Field(
        default=None, alias="AllowedProviderModelIds"
    )


class ProviderModelsForModelGateway(ModelGatewayBaseModel):
    provider_model_id: Optional[str] = Field(default=None, alias="ProviderModelId")
    model_name: Optional[str] = Field(default=None, alias="ModelName")


class ProviderSpecForModelGateway(ModelGatewayBaseModel):
    base_url: Optional[str] = Field(default=None, alias="BaseUrl")


class ProvidersForModelGateway(ModelGatewayBaseModel):
    provider_id: Optional[str] = Field(default=None, alias="ProviderId")
    provider_name: Optional[str] = Field(default=None, alias="ProviderName")
    model_gateway_id: Optional[str] = Field(default=None, alias="ModelGatewayId")
    base_url: Optional[str] = Field(default=None, alias="BaseUrl")
    provider_type: Optional[str] = Field(default=None, alias="ProviderType")
    protocols: Optional[list[str]] = Field(default=None, alias="Protocols")
    provider_source: Optional[str] = Field(default=None, alias="ProviderSource")
    provider_spec: Optional[ProviderSpecForModelGateway] = Field(
        default=None, alias="ProviderSpec"
    )
    credentials: Optional[CredentialsForModelGateway] = Field(
        default=None, alias="Credentials"
    )
    provider_models: Optional[list[ProviderModelsForModelGateway]] = Field(
        default=None, alias="ProviderModels"
    )
    fallback_provider_model_names: Optional[list[str]] = Field(
        default=None, alias="FallbackProviderModelNames"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")
    tags: Optional[list[TagsForModelGateway]] = Field(default=None, alias="Tags")
    created_at: Optional[str] = Field(default=None, alias="CreatedAt")
    updated_at: Optional[str] = Field(default=None, alias="UpdatedAt")


class RetryPolicyForModelGateway(ModelGatewayBaseModel):
    enable: Optional[bool] = Field(default=None, alias="Enable")
    max_retries: Optional[int] = Field(default=None, alias="MaxRetries")


class TagFiltersForModelGateway(ModelGatewayBaseModel):
    key: Optional[str] = Field(default=None, alias="Key")
    values: Optional[list[str]] = Field(default=None, alias="Values")


class TagsForModelGateway(ModelGatewayBaseModel):
    key: str = Field(..., alias="Key")
    value: Optional[str] = Field(default=None, alias="Value")


class TokenRateLimitConfigForModelGateway(ModelGatewayBaseModel):
    enable: Optional[bool] = Field(default=None, alias="Enable")
    rules: Optional[list[TokenRateLimitRulesForModelGateway]] = Field(
        default=None, alias="Rules"
    )


class TokenRateLimitRulesForModelGateway(ModelGatewayBaseModel):
    enable: Optional[bool] = Field(default=None, alias="Enable")
    time_window: Optional[int] = Field(default=None, alias="TimeWindow")
    value: Optional[int] = Field(default=None, alias="Value")


# CreateModelGateway - Request
class ProvidersItemForCreateModelGateway(ModelGatewayBaseModel):
    provider_type: Optional[str] = Field(default=None, alias="ProviderType")
    provider_name: str = Field(..., alias="ProviderName")
    protocols: Optional[list[str]] = Field(default=None, alias="Protocols")
    provider_source: Optional[str] = Field(default=None, alias="ProviderSource")
    provider_spec: Optional[ProviderSpecForModelGateway] = Field(
        default=None, alias="ProviderSpec"
    )
    credentials: Optional[CredentialsForModelGateway] = Field(
        default=None, alias="Credentials"
    )
    provider_models: Optional[list[ProviderModelsForModelGateway]] = Field(
        default=None, alias="ProviderModels"
    )
    fallback_provider_model_names: Optional[list[str]] = Field(
        default=None, alias="FallbackProviderModelNames"
    )


class CreateModelGatewayRequest(ModelGatewayBaseModel):
    type: str = Field(..., alias="Type")
    apig_gateway_id: Optional[str] = Field(default=None, alias="ApigGatewayId")
    providers: Optional[list[ProvidersItemForCreateModelGateway]] = Field(
        default=None, alias="Providers"
    )
    consumer: ConsumerForCreateModelGateway = Field(..., alias="Consumer")
    retry_policy: Optional[RetryPolicyForModelGateway] = Field(
        default=None, alias="RetryPolicy"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")
    tags: Optional[list[TagsForModelGateway]] = Field(default=None, alias="Tags")


# CreateModelGateway - Response
class CreateModelGatewayResponse(ModelGatewayBaseModel):
    model_gateway_id: Optional[str] = Field(default=None, alias="ModelGatewayId")


# ListModelGateways - Request
class ListModelGatewaysRequest(ModelGatewayBaseModel):
    status: Optional[str] = Field(default=None, alias="Status")
    page_number: Optional[int] = Field(default=None, alias="PageNumber")
    page_size: Optional[int] = Field(default=None, alias="PageSize")
    tag_filters: Optional[list[TagFiltersForModelGateway]] = Field(
        default=None, alias="TagFilters"
    )


# ListModelGateways - Response
class ListModelGatewaysResponse(ModelGatewayBaseModel):
    total: Optional[int] = Field(default=None, alias="Total")
    model_gateways: Optional[list[ModelGatewaysForModelGateway]] = Field(
        default=None, alias="ModelGateways"
    )


# CreateModelGatewayProvider - Request
class CreateModelGatewayProviderRequest(ModelGatewayBaseModel):
    model_gateway_id: str = Field(..., alias="ModelGatewayId")
    provider_type: str = Field(..., alias="ProviderType")
    provider_name: str = Field(..., alias="ProviderName")
    protocols: Optional[list[str]] = Field(default=None, alias="Protocols")
    provider_source: Optional[str] = Field(default=None, alias="ProviderSource")
    provider_spec: Optional[ProviderSpecForModelGateway] = Field(
        default=None, alias="ProviderSpec"
    )
    credentials: Optional[CredentialsForModelGateway] = Field(
        default=None, alias="Credentials"
    )
    provider_models: Optional[list[ProviderModelsForModelGateway]] = Field(
        default=None, alias="ProviderModels"
    )
    fallback_provider_model_names: Optional[list[str]] = Field(
        default=None, alias="FallbackProviderModelNames"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")
    tags: Optional[list[TagsForModelGateway]] = Field(default=None, alias="Tags")


# CreateModelGatewayProvider - Response
class CreateModelGatewayProviderResponse(ModelGatewayBaseModel):
    provider_id: Optional[str] = Field(default=None, alias="ProviderId")


# UpdateModelGatewayProvider - Request
class UpdateModelGatewayProviderRequest(ModelGatewayBaseModel):
    provider_id: str = Field(..., alias="ProviderId")
    provider_name: Optional[str] = Field(default=None, alias="ProviderName")
    protocols: Optional[list[str]] = Field(default=None, alias="Protocols")
    provider_source: Optional[str] = Field(default=None, alias="ProviderSource")
    provider_spec: Optional[ProviderSpecForModelGateway] = Field(
        default=None, alias="ProviderSpec"
    )
    credentials: Optional[CredentialsForModelGateway] = Field(
        default=None, alias="Credentials"
    )
    provider_models: Optional[list[ProviderModelsForModelGateway]] = Field(
        default=None, alias="ProviderModels"
    )
    fallback_provider_model_names: Optional[list[str]] = Field(
        default=None, alias="FallbackProviderModelNames"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")


# UpdateModelGatewayProvider - Response
class UpdateModelGatewayProviderResponse(ModelGatewayBaseModel):
    provider_id: Optional[str] = Field(default=None, alias="ProviderId")


# DeleteModelGatewayProvider - Request
class DeleteModelGatewayProviderRequest(ModelGatewayBaseModel):
    provider_id: str = Field(..., alias="ProviderId")


# DeleteModelGatewayProvider - Response
class DeleteModelGatewayProviderResponse(ModelGatewayBaseModel):
    pass


# GetModelGatewayProvider - Request
class GetModelGatewayProviderRequest(ModelGatewayBaseModel):
    provider_id: str = Field(..., alias="ProviderId")


# GetModelGatewayProvider - Response
class GetModelGatewayProviderResponse(ModelGatewayBaseModel):
    provider: Optional[ProvidersForModelGateway] = Field(default=None, alias="Provider")


# ListModelGatewayProviders - Request
class ListModelGatewayProvidersRequest(ModelGatewayBaseModel):
    provider_name: Optional[str] = Field(default=None, alias="ProviderName")
    model_gateway_id: str = Field(..., alias="ModelGatewayId")
    page_number: Optional[int] = Field(default=None, alias="PageNumber")
    page_size: Optional[int] = Field(default=None, alias="PageSize")
    tag_filters: Optional[list[TagFiltersForModelGateway]] = Field(
        default=None, alias="TagFilters"
    )


# ListModelGatewayProviders - Response
class ListModelGatewayProvidersResponse(ModelGatewayBaseModel):
    total: Optional[int] = Field(default=None, alias="Total")
    providers: Optional[list[ProvidersForModelGateway]] = Field(
        default=None, alias="Providers"
    )


# CreateModelGatewayConsumer - Request
class CreateModelGatewayConsumerRequest(ModelGatewayBaseModel):
    consumer_name: str = Field(..., alias="ConsumerName")
    model_gateway_id: str = Field(..., alias="ModelGatewayId")
    authz_config: Optional[AuthzConfigForModelGateway] = Field(
        default=None, alias="AuthzConfig"
    )
    token_rate_limit_config: Optional[TokenRateLimitConfigForModelGateway] = Field(
        default=None, alias="TokenRateLimitConfig"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")
    tags: Optional[list[TagsForModelGateway]] = Field(default=None, alias="Tags")


# CreateModelGatewayConsumer - Response
class CreateModelGatewayConsumerResponse(ModelGatewayBaseModel):
    consumer_id: Optional[str] = Field(default=None, alias="ConsumerId")


# UpdateModelGatewayConsumer - Request
class UpdateModelGatewayConsumerRequest(ModelGatewayBaseModel):
    consumer_id: str = Field(..., alias="ConsumerId")
    consumer_name: Optional[str] = Field(default=None, alias="ConsumerName")
    authz_config: Optional[AuthzConfigForModelGateway] = Field(
        default=None, alias="AuthzConfig"
    )
    token_rate_limit_config: Optional[TokenRateLimitConfigForModelGateway] = Field(
        default=None, alias="TokenRateLimitConfig"
    )
    comments: Optional[str] = Field(default=None, alias="Comments")


# UpdateModelGatewayConsumer - Response
class UpdateModelGatewayConsumerResponse(ModelGatewayBaseModel):
    consumer_id: Optional[str] = Field(default=None, alias="ConsumerId")


# DeleteModelGatewayConsumer - Request
class DeleteModelGatewayConsumerRequest(ModelGatewayBaseModel):
    consumer_id: str = Field(..., alias="ConsumerId")


# DeleteModelGatewayConsumer - Response
class DeleteModelGatewayConsumerResponse(ModelGatewayBaseModel):
    pass


# GetModelGatewayConsumer - Request
class GetModelGatewayConsumerRequest(ModelGatewayBaseModel):
    consumer_id: str = Field(..., alias="ConsumerId")


# GetModelGatewayConsumer - Response
class GetModelGatewayConsumerResponse(ModelGatewayBaseModel):
    consumer: Optional[ConsumersForModelGateway] = Field(default=None, alias="Consumer")


# ListModelGatewayConsumers - Request
class ListModelGatewayConsumersRequest(ModelGatewayBaseModel):
    consumer_name: Optional[str] = Field(default=None, alias="ConsumerName")
    model_gateway_id: str = Field(..., alias="ModelGatewayId")
    page_number: Optional[int] = Field(default=None, alias="PageNumber")
    page_size: Optional[int] = Field(default=None, alias="PageSize")
    tag_filters: Optional[list[TagFiltersForModelGateway]] = Field(
        default=None, alias="TagFilters"
    )


# ListModelGatewayConsumers - Response
class ListModelGatewayConsumersResponse(ModelGatewayBaseModel):
    total: Optional[int] = Field(default=None, alias="Total")
    consumers: Optional[list[ConsumersForModelGateway]] = Field(
        default=None, alias="Consumers"
    )
