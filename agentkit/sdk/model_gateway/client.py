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

from typing import Dict

from agentkit.client import BaseAgentkitClient

from .types import (
    CreateModelGatewayRequest,
    CreateModelGatewayConsumerRequest,
    CreateModelGatewayConsumerResponse,
    CreateModelGatewayProviderRequest,
    CreateModelGatewayProviderResponse,
    CreateModelGatewayResponse,
    DeleteModelGatewayConsumerRequest,
    DeleteModelGatewayConsumerResponse,
    DeleteModelGatewayProviderRequest,
    DeleteModelGatewayProviderResponse,
    GetModelGatewayConsumerRequest,
    GetModelGatewayConsumerResponse,
    GetModelGatewayProviderRequest,
    GetModelGatewayProviderResponse,
    ListModelGatewayConsumersRequest,
    ListModelGatewayConsumersResponse,
    ListModelGatewaysRequest,
    ListModelGatewaysResponse,
    ListModelGatewayProvidersRequest,
    ListModelGatewayProvidersResponse,
    UpdateModelGatewayConsumerRequest,
    UpdateModelGatewayConsumerResponse,
    UpdateModelGatewayProviderRequest,
    UpdateModelGatewayProviderResponse,
)


class AgentkitModelGatewayClient(BaseAgentkitClient):
    """AgentKit Model Gateway Management Service"""

    API_ACTIONS: Dict[str, str] = {
        "CreateModelGateway": "CreateModelGateway",
        "CreateModelGatewayConsumer": "CreateModelGatewayConsumer",
        "CreateModelGatewayProvider": "CreateModelGatewayProvider",
        "DeleteModelGatewayConsumer": "DeleteModelGatewayConsumer",
        "DeleteModelGatewayProvider": "DeleteModelGatewayProvider",
        "GetModelGatewayConsumer": "GetModelGatewayConsumer",
        "GetModelGatewayProvider": "GetModelGatewayProvider",
        "ListModelGatewayConsumers": "ListModelGatewayConsumers",
        "ListModelGateways": "ListModelGateways",
        "ListModelGatewayProviders": "ListModelGatewayProviders",
        "UpdateModelGatewayConsumer": "UpdateModelGatewayConsumer",
        "UpdateModelGatewayProvider": "UpdateModelGatewayProvider",
    }

    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        region: str = "",
        session_token: str = "",
    ) -> None:
        super().__init__(
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            session_token=session_token,
            service_name="model_gateway",
        )

    def create_model_gateway_consumer(
        self, request: CreateModelGatewayConsumerRequest
    ) -> CreateModelGatewayConsumerResponse:
        return self._invoke_api(
            api_action="CreateModelGatewayConsumer",
            request=request,
            response_type=CreateModelGatewayConsumerResponse,
        )

    def create_model_gateway(
        self, request: CreateModelGatewayRequest
    ) -> CreateModelGatewayResponse:
        return self._invoke_api(
            api_action="CreateModelGateway",
            request=request,
            response_type=CreateModelGatewayResponse,
        )

    def create_model_gateway_provider(
        self, request: CreateModelGatewayProviderRequest
    ) -> CreateModelGatewayProviderResponse:
        return self._invoke_api(
            api_action="CreateModelGatewayProvider",
            request=request,
            response_type=CreateModelGatewayProviderResponse,
        )

    def delete_model_gateway_consumer(
        self, request: DeleteModelGatewayConsumerRequest
    ) -> DeleteModelGatewayConsumerResponse:
        return self._invoke_api(
            api_action="DeleteModelGatewayConsumer",
            request=request,
            response_type=DeleteModelGatewayConsumerResponse,
        )

    def delete_model_gateway_provider(
        self, request: DeleteModelGatewayProviderRequest
    ) -> DeleteModelGatewayProviderResponse:
        return self._invoke_api(
            api_action="DeleteModelGatewayProvider",
            request=request,
            response_type=DeleteModelGatewayProviderResponse,
        )

    def get_model_gateway_consumer(
        self, request: GetModelGatewayConsumerRequest
    ) -> GetModelGatewayConsumerResponse:
        return self._invoke_api(
            api_action="GetModelGatewayConsumer",
            request=request,
            response_type=GetModelGatewayConsumerResponse,
        )

    def get_model_gateway_provider(
        self, request: GetModelGatewayProviderRequest
    ) -> GetModelGatewayProviderResponse:
        return self._invoke_api(
            api_action="GetModelGatewayProvider",
            request=request,
            response_type=GetModelGatewayProviderResponse,
        )

    def list_model_gateway_consumers(
        self, request: ListModelGatewayConsumersRequest
    ) -> ListModelGatewayConsumersResponse:
        return self._invoke_api(
            api_action="ListModelGatewayConsumers",
            request=request,
            response_type=ListModelGatewayConsumersResponse,
        )

    def list_model_gateways(
        self, request: ListModelGatewaysRequest
    ) -> ListModelGatewaysResponse:
        return self._invoke_api(
            api_action="ListModelGateways",
            request=request,
            response_type=ListModelGatewaysResponse,
        )

    def list_model_gateway_providers(
        self, request: ListModelGatewayProvidersRequest
    ) -> ListModelGatewayProvidersResponse:
        return self._invoke_api(
            api_action="ListModelGatewayProviders",
            request=request,
            response_type=ListModelGatewayProvidersResponse,
        )

    def update_model_gateway_consumer(
        self, request: UpdateModelGatewayConsumerRequest
    ) -> UpdateModelGatewayConsumerResponse:
        return self._invoke_api(
            api_action="UpdateModelGatewayConsumer",
            request=request,
            response_type=UpdateModelGatewayConsumerResponse,
        )

    def update_model_gateway_provider(
        self, request: UpdateModelGatewayProviderRequest
    ) -> UpdateModelGatewayProviderResponse:
        return self._invoke_api(
            api_action="UpdateModelGatewayProvider",
            request=request,
            response_type=UpdateModelGatewayProviderResponse,
        )
