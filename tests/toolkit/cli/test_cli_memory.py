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

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class _FakeMemoryClient:
    instances = []
    last_request = None

    def __init__(self, **kwargs):
        self.region = kwargs.get("region", "")
        _FakeMemoryClient.instances.append(self)

    def create_memory_collection(self, request):
        _FakeMemoryClient.last_request = request
        return SimpleNamespace(memory_id="mem-created", status="Ready")


@pytest.fixture(autouse=True)
def _clear_cloud_provider_env(monkeypatch):
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)


@pytest.fixture(autouse=True)
def _fake_memory_client(monkeypatch):
    from agentkit.toolkit.cli import cli_memory

    _FakeMemoryClient.instances = []
    _FakeMemoryClient.last_request = None
    monkeypatch.setattr(cli_memory, "AgentkitMemoryClient", _FakeMemoryClient)


def test_create_help_points_to_provider_types_for_supported_values():
    from agentkit.toolkit.cli.cli import app

    result = runner.invoke(app, ["memory", "create", "--help"])

    assert result.exit_code == 0
    assert "--provider-type" in result.output
    assert "provider-types" in result.output
    assert "MEM0 | VIKINGDB_MEMORY" not in result.output


def test_provider_types_lists_mem0_for_volcengine(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")

    result = runner.invoke(app, ["memory", "provider-types"])

    assert result.exit_code == 0
    assert "Cloud provider: volcengine" in result.output
    assert "MEM0" in result.output
    assert "mem0" in result.output
    assert "VIKINGDB_MEMORY" in result.output


def test_provider_types_hides_mem0_row_for_byteplus(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")

    result = runner.invoke(app, ["memory", "provider-types"])

    assert result.exit_code == 0
    assert "Cloud provider: byteplus" in result.output
    assert "VIKINGDB_MEMORY" in result.output
    assert "MEM0 is not" in result.output
    assert "supported on BytePlus" in result.output
    assert not any(
        "MEM0" in line and "mem0" in line for line in result.output.splitlines()
    )


def test_create_defaults_provider_type_to_mem0_for_volcengine(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")

    result = runner.invoke(app, ["memory", "create", "--name", "demo_memory"])

    assert result.exit_code == 0
    assert _FakeMemoryClient.last_request.provider_type == "MEM0"


def test_create_defaults_provider_type_to_vikingdb_for_byteplus(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")

    result = runner.invoke(app, ["memory", "create", "--name", "demo_memory"])

    assert result.exit_code == 0
    assert _FakeMemoryClient.last_request.provider_type == "VIKINGDB_MEMORY"


def test_create_rejects_mem0_for_byteplus(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")

    result = runner.invoke(
        app,
        ["memory", "create", "--name", "demo_memory", "--provider-type", "mem0"],
    )

    assert result.exit_code == 1
    assert "MEM0 provider type is not supported for BytePlus yet" in result.output
    assert _FakeMemoryClient.instances == []
    assert _FakeMemoryClient.last_request is None


def test_create_json_rejects_mem0_for_byteplus(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")

    result = runner.invoke(
        app,
        [
            "memory",
            "create",
            "--name",
            "ignored_by_json",
            "--json",
            '{"Name": "demo_memory", "ProviderType": "MEM0"}',
        ],
    )

    assert result.exit_code == 1
    assert "MEM0 provider type is not supported for BytePlus yet" in result.output
    assert _FakeMemoryClient.instances == []
    assert _FakeMemoryClient.last_request is None


def test_create_json_defaults_provider_type_to_vikingdb_for_byteplus(monkeypatch):
    from agentkit.toolkit.cli.cli import app

    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")

    result = runner.invoke(
        app,
        [
            "memory",
            "create",
            "--name",
            "ignored_by_json",
            "--json",
            '{"Name": "demo_memory"}',
        ],
    )

    assert result.exit_code == 0
    assert _FakeMemoryClient.last_request.provider_type == "VIKINGDB_MEMORY"
