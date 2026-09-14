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

from agentkit.sdk.tools import types as tools_types


def test_create_tool_request_serializes_enable_mcp_alias() -> None:
    request = tools_types.CreateToolRequest(
        name="mcp-tool",
        tool_type="CodeEnv",
        enable_mcp=True,
    )

    assert request.model_dump(by_alias=True, exclude_none=True) == {
        "EnableMcp": True,
        "Name": "mcp-tool",
        "ToolType": "CodeEnv",
    }


def test_update_tool_request_preserves_explicit_false_enable_mcp() -> None:
    request = tools_types.UpdateToolRequest(
        tool_id="tool-1",
        enable_mcp=False,
    )

    assert request.model_dump(by_alias=True, exclude_none=True) == {
        "EnableMcp": False,
        "ToolId": "tool-1",
    }


def test_get_and_list_tool_responses_parse_enable_mcp() -> None:
    get_response = tools_types.GetToolResponse(EnableMcp=True)
    list_response = tools_types.ListToolsResponse(
        Tools=[{"ToolId": "tool-1", "EnableMcp": False}]
    )

    assert get_response.enable_mcp is True
    assert list_response.tools is not None
    assert list_response.tools[0].enable_mcp is False
