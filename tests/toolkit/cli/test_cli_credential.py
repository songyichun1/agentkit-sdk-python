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

"""Tests for the credential commands (add / list / delete)."""

import json

from typer.testing import CliRunner

import agentkit.sdk.identity.client as client_mod
from agentkit.toolkit.cli.cli import app
from agentkit.sdk.identity import types as it

runner = CliRunner()


def test_identity_client_uses_agent_identity_service_endpoint():
    client = client_mod.AgentkitIdentityClient(
        access_key="ak",
        secret_key="sk",
        region="cn-beijing",
    )

    assert client.service == "id"
    assert client.host == "id.cn-beijing.volcengineapi.com"
    assert client.api_version == "2025-10-30"
    assert client.api_info["ListInboundAuthConfigs"].query == {
        "Action": "ListInboundAuthConfigs",
        "Version": "2025-10-30",
    }


def _config(config_id, name):
    return it.InboundAuthConfigForList.model_validate(
        {
            "Trn": f"trn:id:cn-beijing:1234567890:authconfig/{config_id}",
            "InboundAuthConfigId": config_id,
            "ConfigName": name,
            "InstanceId": f"inst-{config_id}",
            "AuthType": "ApiKey",
            "CreatedAt": "2025-10-30T07:59:24Z",
            "UpdatedAt": "2025-10-30T07:59:24Z",
        }
    )


# --- add credential ---------------------------------------------------------


def test_add_credential_sends_api_key_request(monkeypatch):
    captured = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def create_inbound_auth_config(self, request):
            captured["request"] = request
            return it.CreateInboundAuthConfigResponse.model_validate(
                {
                    "Trn": "trn:id:cn-beijing:1234567890:authconfig/iac-123",
                    "InboundAuthConfigId": "iac-123",
                    "ConfigName": "my-openai-key",
                    "AuthType": "ApiKey",
                    "CreatedAt": "2025-10-30T07:59:24Z",
                    "UpdatedAt": "2025-10-30T07:59:24Z",
                }
            )

    # The commands import the client lazily via ``from ...client import``, which
    # re-reads from the source module at call time — so patching it there works.
    monkeypatch.setattr(client_mod, "AgentkitIdentityClient", _FakeClient)

    result = runner.invoke(
        app,
        [
            "add",
            "credential",
            "--type",
            "api-key",
            "--name",
            "my-openai-key",
            "--api-key",
            "sk-123",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "iac-123" in result.output
    req = captured["request"]
    assert req.auth_type == "ApiKey"
    assert req.config_name == "my-openai-key"
    assert req.api_key_auth_configs[0].api_key_name == "my-openai-key"
    assert req.api_key_auth_configs[0].api_key == "sk-123"


def test_add_credential_invalid_type_fails():
    result = runner.invoke(
        app, ["add", "credential", "--type", "oauth", "--name", "x", "--api-key", "y"]
    )
    assert result.exit_code == 1
    assert "invalid --type" in result.output


def test_add_credential_requires_api_key():
    result = runner.invoke(
        app, ["add", "credential", "--type", "api-key", "--name", "x"]
    )
    assert result.exit_code == 1
    assert "--api-key is required" in result.output


def test_inbound_auth_models_match_openapi_contract():
    request = it.ListInboundAuthConfigsRequest(
        page_number=1,
        page_size=10,
        auth_type="ApiKey",
        instance_id="123",
    )
    assert request.model_dump(by_alias=True, exclude_none=True) == {
        "PageNumber": 1,
        "PageSize": 10,
        "AuthType": "ApiKey",
        "InstanceId": "123",
    }

    api_key_info = it.ApiKeyInfo(
        location="Header",
        parameter_name="ApiKey",
        prefix="Bearer",
    )
    assert api_key_info.model_dump(by_alias=True, exclude_none=True) == {
        "Location": "Header",
        "ParameterName": "ApiKey",
        "Prefix": "Bearer",
    }

    delete_response = it.DeleteInboundAuthConfigResponse.model_validate({})
    assert delete_response.model_dump(by_alias=True, exclude_none=True) == {}


def test_list_response_accepts_metadata_without_parameter_name():
    response = it.ListInboundAuthConfigsResponse.model_validate(
        {
            "PageNumber": 1,
            "PageSize": 10,
            "TotalCount": 1,
            "InboundAuthConfigs": [
                {
                    "Trn": "trn:id:cn-beijing:1234567890:authconfig/iac-1",
                    "InboundAuthConfigId": "iac-1",
                    "ConfigName": "key-a",
                    "InstanceId": "inst-iac-1",
                    "AuthType": "ApiKey",
                    "ApiKeyAuthConfigs": [
                        {
                            "ApiKeyName": "key-a",
                            "ApiKeyMetadata": [{"Location": "HEADER"}],
                        }
                    ],
                    "CreatedAt": "2025-10-30T07:59:24Z",
                    "UpdatedAt": "2025-10-30T07:59:24Z",
                }
            ],
        }
    )

    metadata = (
        response.inbound_auth_configs[0].api_key_auth_configs[0].api_key_metadata[0]
    )
    assert metadata.location == "HEADER"
    assert metadata.parameter_name is None


# --- list credentials -------------------------------------------------------


def _patch_list(monkeypatch, configs):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_inbound_auth_configs(self, request):
            return it.ListInboundAuthConfigsResponse.model_validate(
                {
                    "InboundAuthConfigs": [
                        c.model_dump(by_alias=True, exclude_none=True) for c in configs
                    ],
                    "PageNumber": request.page_number,
                    "PageSize": request.page_size,
                    "TotalCount": len(configs),
                }
            )

    monkeypatch.setattr(client_mod, "AgentkitIdentityClient", _FakeClient)
    return _FakeClient


def test_list_credentials_table(monkeypatch):
    _patch_list(monkeypatch, [_config("iac-1", "my-openai-key")])
    result = runner.invoke(app, ["list", "credentials"])
    assert result.exit_code == 0, result.output
    assert "InstanceId" in result.output
    assert "inst-iac-1" in result.output


def test_list_credentials_quiet_prints_instance_ids(monkeypatch):
    _patch_list(monkeypatch, [_config("iac-1", "key-a"), _config("iac-2", "key-b")])
    result = runner.invoke(app, ["list", "credentials", "--quiet"])
    assert result.exit_code == 0, result.output
    assert result.output.split() == ["inst-iac-1", "inst-iac-2"]


def test_list_credentials_json(monkeypatch):
    _patch_list(monkeypatch, [_config("iac-1", "key-a")])
    result = runner.invoke(app, ["list", "credentials", "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [c["ConfigName"] for c in data] == ["key-a"]


def test_list_credentials_uses_page_number_pagination(monkeypatch):
    seen_pages = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_inbound_auth_configs(self, request):
            seen_pages.append(request.page_number)
            assert request.page_size == 1
            config = _config(f"iac-{request.page_number}", f"key-{request.page_number}")
            return it.ListInboundAuthConfigsResponse.model_validate(
                {
                    "InboundAuthConfigs": [
                        config.model_dump(by_alias=True, exclude_none=True)
                    ],
                    "PageNumber": request.page_number,
                    "PageSize": request.page_size,
                    "TotalCount": 2,
                }
            )

    monkeypatch.setattr(client_mod, "AgentkitIdentityClient", _FakeClient)

    result = runner.invoke(app, ["list", "credentials", "--quiet", "--limit", "1"])

    assert result.exit_code == 0, result.output
    assert seen_pages == [1, 2]
    assert result.output.split() == ["inst-iac-1", "inst-iac-2"]


# --- delete credential ------------------------------------------------------


def test_delete_credential_resolves_name_to_id(monkeypatch):
    deleted = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_inbound_auth_configs(self, request):
            return it.ListInboundAuthConfigsResponse.model_validate(
                {
                    "InboundAuthConfigs": [
                        _config("iac-1", "key-a").model_dump(by_alias=True),
                        _config("iac-2", "key-b").model_dump(by_alias=True),
                    ],
                    "PageNumber": request.page_number,
                    "PageSize": request.page_size,
                    "TotalCount": 2,
                }
            )

        def delete_inbound_auth_config(self, request):
            deleted.append(request.inbound_auth_config_id)
            return it.DeleteInboundAuthConfigResponse.model_validate(
                {"InboundAuthConfigId": request.inbound_auth_config_id}
            )

    monkeypatch.setattr(client_mod, "AgentkitIdentityClient", _FakeClient)

    result = runner.invoke(app, ["delete", "credential", "key-b"])
    assert result.exit_code == 0, result.output
    assert deleted == ["iac-2"]


def test_delete_credential_not_found(monkeypatch):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_inbound_auth_configs(self, request):
            return it.ListInboundAuthConfigsResponse.model_validate(
                {
                    "InboundAuthConfigs": [],
                    "PageNumber": request.page_number,
                    "PageSize": request.page_size,
                    "TotalCount": 0,
                }
            )

        def delete_inbound_auth_config(self, request):  # pragma: no cover
            raise AssertionError("delete should not be called")

    monkeypatch.setattr(client_mod, "AgentkitIdentityClient", _FakeClient)

    result = runner.invoke(app, ["delete", "credential", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output
