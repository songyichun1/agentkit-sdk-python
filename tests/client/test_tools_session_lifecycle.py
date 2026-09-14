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
from agentkit.sdk.tools.client import AgentkitToolsClient


def test_pause_session_models_use_openapi_aliases() -> None:
    request = tools_types.PauseSessionRequest(
        session_id="session-1",
        tool_id="tool-1",
    )
    response = tools_types.PauseSessionResponse(
        SessionId="session-1",
        Status="Paused",
    )

    assert request.model_dump(by_alias=True, exclude_none=True) == {
        "SessionId": "session-1",
        "ToolId": "tool-1",
    }
    assert response.session_id == "session-1"
    assert response.status == "Paused"


def test_resume_session_models_use_openapi_aliases() -> None:
    request = tools_types.ResumeSessionRequest(
        SessionId="session-1",
        ToolId="tool-1",
        Ttl=30,
        TtlUnit="minute",
    )
    response = tools_types.ResumeSessionResponse(
        SessionId="session-1",
        Status="Ready",
        ExpireAt="2026-09-11T12:00:00+08:00",
    )

    assert request.model_dump(by_alias=True, exclude_none=True) == {
        "SessionId": "session-1",
        "ToolId": "tool-1",
        "Ttl": 30,
        "TtlUnit": "minute",
    }
    assert response.session_id == "session-1"
    assert response.status == "Ready"
    assert response.expire_at == "2026-09-11T12:00:00+08:00"


def test_session_lifecycle_client_methods_dispatch_expected_actions(
    monkeypatch,
) -> None:
    client = object.__new__(AgentkitToolsClient)
    calls = []

    def fake_invoke_api(*, api_action, request, response_type):
        calls.append((api_action, request, response_type))
        return response_type()

    monkeypatch.setattr(client, "_invoke_api", fake_invoke_api)
    pause_request = tools_types.PauseSessionRequest(
        session_id="session-1",
        tool_id="tool-1",
    )
    resume_request = tools_types.ResumeSessionRequest(
        session_id="session-1",
        tool_id="tool-1",
    )

    client.pause_session(pause_request)
    client.resume_session(resume_request)

    assert AgentkitToolsClient.API_ACTIONS["PauseSession"] == "PauseSession"
    assert AgentkitToolsClient.API_ACTIONS["ResumeSession"] == "ResumeSession"
    assert calls == [
        ("PauseSession", pause_request, tools_types.PauseSessionResponse),
        ("ResumeSession", resume_request, tools_types.ResumeSessionResponse),
    ]


def test_snapshot_models_support_type_filter_metadata_and_retention() -> None:
    create_request = tools_types.CreateSessionSnapshotRequest(
        session_id="session-1",
        tool_id="tool-1",
        retention_count=3,
    )
    list_request = tools_types.ListSessionSnapshotsRequest(
        tool_id="tool-1",
        snapshot_type="USER",
    )
    response = tools_types.ListSessionSnapshotsResponse(
        Snapshots=[
            {
                "SnapshotId": "snapshot-1",
                "SnapshotType": "PAUSE",
                "SessionMetadata": [
                    {"Key": "source", "Value": "auto", "Type": "SYSTEM"}
                ],
            }
        ]
    )
    get_response = tools_types.GetSessionSnapshotResponse(
        Snapshot={
            "SnapshotId": "snapshot-2",
            "SnapshotType": "USER",
            "UserSessionId": "user-session-1",
            "SessionMetadata": [{"Key": "purpose", "Value": "checkpoint"}],
        }
    )

    assert create_request.model_dump(by_alias=True, exclude_none=True) == {
        "RetentionCount": 3,
        "SessionId": "session-1",
        "ToolId": "tool-1",
    }
    assert list_request.model_dump(by_alias=True, exclude_none=True) == {
        "SnapshotType": "USER",
        "ToolId": "tool-1",
    }
    assert response.snapshots is not None
    assert response.snapshots[0].snapshot_type == "PAUSE"
    assert response.snapshots[0].session_metadata is not None
    assert response.snapshots[0].session_metadata[0].key == "source"
    assert get_response.snapshot is not None
    assert get_response.snapshot.snapshot_type == "USER"
    assert get_response.snapshot.user_session_id == "user-session-1"
    assert get_response.snapshot.session_metadata is not None
    assert get_response.snapshot.session_metadata[0].value == "checkpoint"
