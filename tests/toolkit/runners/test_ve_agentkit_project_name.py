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

from types import SimpleNamespace

from agentkit.sdk.runtime import types as runtime_types
from agentkit.toolkit.config import AUTH_TYPE_CUSTOM_JWT, CommonConfig
from agentkit.toolkit.runners.ve_agentkit import (
    VeAgentkitRunnerConfig,
    VeAgentkitRuntimeRunner,
)


def test_create_runtime_uses_configured_project_name(monkeypatch) -> None:
    create_calls = []

    class FakeRuntimeClient:
        def create_runtime(self, request):
            create_calls.append(request)
            return runtime_types.CreateRuntimeResponse(RuntimeId="r-test")

    runner = VeAgentkitRuntimeRunner()
    monkeypatch.setattr(
        runner, "_get_runtime_client", lambda region="": FakeRuntimeClient()
    )
    monkeypatch.setattr(
        runner,
        "_wait_for_runtime_status",
        lambda **kwargs: (True, SimpleNamespace(network_configurations=[]), None),
    )

    result = runner._create_new_runtime(
        VeAgentkitRunnerConfig(
            common_config=CommonConfig(agent_name="test-agent"),
            project_name="lh-test",
            runtime_name="test-runtime",
            runtime_role_name="test-role",
            runtime_auth_type=AUTH_TYPE_CUSTOM_JWT,
            runtime_jwt_discovery_url="https://example.com/.well-known/openid-configuration",
            image_url="example.com/test/image:latest",
        )
    )

    assert result.success is True
    assert create_calls[0].project_name == "lh-test"
