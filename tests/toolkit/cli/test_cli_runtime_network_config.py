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

import inspect
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner


runner = CliRunner()


class _FakeRuntimeClient:
    instances = []
    last_request = None

    def __init__(self, **kwargs):
        self.region = kwargs.get("region", "")
        _FakeRuntimeClient.instances.append(self)

    def create_runtime(self, request):
        _FakeRuntimeClient.last_request = request
        return SimpleNamespace(runtime_id="rt-created")


def _runtime_create_args(*extra_args):
    return [
        "runtime",
        "create",
        "--name",
        "demo-runtime",
        "--role-name",
        "demo-role",
        "--artifact-type",
        "image",
        "--artifact-url",
        "example.com/demo:latest",
        *extra_args,
    ]


@pytest.fixture(autouse=True)
def _fake_runtime_client(monkeypatch):
    from agentkit.toolkit.cli import cli_runtime

    _FakeRuntimeClient.instances = []
    _FakeRuntimeClient.last_request = None
    monkeypatch.setattr(cli_runtime, "AgentkitRuntimeClient", _FakeRuntimeClient)


def test_create_runtime_artifact_type_help_uses_image_and_remains_required():
    from agentkit.toolkit.cli.cli_runtime import create_runtime_command

    option = (
        inspect.signature(create_runtime_command).parameters["artifact_type"].default
    )

    assert option.default is ...
    assert option.help == "Artifact type (e.g., image)"


def test_validate_runtime_create_authorizer_requires_exactly_one_auth_option():
    from agentkit.toolkit.cli.cli_runtime import (
        _validate_runtime_create_authorizer_options,
    )

    with pytest.raises(ValueError):
        _validate_runtime_create_authorizer_options(
            api_key_name=None,
            jwt_discovery_url=None,
        )

    with pytest.raises(ValueError):
        _validate_runtime_create_authorizer_options(
            api_key_name="demo-key",
            jwt_discovery_url="https://issuer.example.com/.well-known/jwks.json",
        )

    _validate_runtime_create_authorizer_options(
        api_key_name="demo-key",
        jwt_discovery_url=None,
    )
    _validate_runtime_create_authorizer_options(
        api_key_name=None,
        jwt_discovery_url="https://issuer.example.com/.well-known/jwks.json",
    )


def test_create_runtime_rejects_missing_auth_option_before_client_init():
    from agentkit.toolkit.cli.cli import app

    result = runner.invoke(app, _runtime_create_args())

    assert result.exit_code == 1
    assert "Exactly one of --apikey-name or --jwt-discovery-url" in result.output
    assert "required" in result.output
    assert _FakeRuntimeClient.instances == []
    assert _FakeRuntimeClient.last_request is None


def test_create_runtime_rejects_conflicting_auth_options_before_client_init():
    from agentkit.toolkit.cli.cli import app

    result = runner.invoke(
        app,
        _runtime_create_args(
            "--apikey-name",
            "demo-key",
            "--jwt-discovery-url",
            "https://issuer.example.com/.well-known/jwks.json",
        ),
    )

    assert result.exit_code == 1
    assert "Exactly one of --apikey-name or --jwt-discovery-url" in result.output
    assert "required" in result.output
    assert _FakeRuntimeClient.instances == []
    assert _FakeRuntimeClient.last_request is None


def test_create_runtime_accepts_api_key_name_auth():
    from agentkit.toolkit.cli.cli import app

    result = runner.invoke(
        app,
        _runtime_create_args(
            "--apikey-name",
            "demo-key",
            "--apikey-location",
            "HEADER",
        ),
    )

    assert result.exit_code == 0
    assert _FakeRuntimeClient.last_request.authorizer_configuration is not None
    authorizer = _FakeRuntimeClient.last_request.authorizer_configuration
    assert authorizer.key_auth.api_key_name == "demo-key"
    assert authorizer.key_auth.api_key_location == "HEADER"
    assert authorizer.custom_jwt_authorizer is None


def test_create_runtime_accepts_jwt_discovery_url_auth():
    from agentkit.toolkit.cli.cli import app

    result = runner.invoke(
        app,
        _runtime_create_args(
            "--jwt-discovery-url",
            "https://issuer.example.com/.well-known/jwks.json",
            "--jwt-allowed-clients",
            "client-a,client-b",
        ),
    )

    assert result.exit_code == 0
    assert _FakeRuntimeClient.last_request.authorizer_configuration is not None
    authorizer = _FakeRuntimeClient.last_request.authorizer_configuration
    assert authorizer.key_auth is None
    assert (
        authorizer.custom_jwt_authorizer.discovery_url
        == "https://issuer.example.com/.well-known/jwks.json"
    )
    assert authorizer.custom_jwt_authorizer.allowed_clients == ["client-a", "client-b"]


def test_build_network_none_when_no_user_intent():
    from agentkit.toolkit.cli.cli_runtime import _build_network_for_create_runtime

    network = _build_network_for_create_runtime(
        vpc_id=None,
        subnet_ids=None,
        enable_private_network=False,
        enable_public_network=True,
        enable_shared_internet_access=False,
    )
    assert network is None


def test_build_network_private_requires_vpc_id():
    from agentkit.toolkit.cli.cli_runtime import _build_network_for_create_runtime

    with pytest.raises(ValueError):
        _build_network_for_create_runtime(
            vpc_id=None,
            subnet_ids=None,
            enable_private_network=True,
            enable_public_network=True,
            enable_shared_internet_access=False,
        )


def test_build_network_disable_public_requires_private():
    from agentkit.toolkit.cli.cli_runtime import _build_network_for_create_runtime

    with pytest.raises(ValueError):
        _build_network_for_create_runtime(
            vpc_id=None,
            subnet_ids=None,
            enable_private_network=False,
            enable_public_network=False,
            enable_shared_internet_access=False,
        )


def test_build_network_vpc_id_implies_private_enabled():
    from agentkit.toolkit.cli.cli_runtime import _build_network_for_create_runtime

    network = _build_network_for_create_runtime(
        vpc_id="vpc-123",
        subnet_ids=None,
        enable_private_network=False,
        enable_public_network=True,
        enable_shared_internet_access=False,
    )
    assert network is not None
    assert network.enable_private_network is True
    assert network.enable_public_network is True
    assert network.vpc_configuration is not None
    assert network.vpc_configuration.vpc_id == "vpc-123"


def test_build_network_shared_internet_access_sets_vpc_field():
    from agentkit.toolkit.cli.cli_runtime import _build_network_for_create_runtime

    network = _build_network_for_create_runtime(
        vpc_id="vpc-123",
        subnet_ids="subnet-1,subnet-2",
        enable_private_network=True,
        enable_public_network=False,
        enable_shared_internet_access=True,
    )
    assert network is not None
    assert network.enable_private_network is True
    assert network.enable_public_network is False
    assert network.vpc_configuration is not None
    assert network.vpc_configuration.enable_shared_internet_access is True
