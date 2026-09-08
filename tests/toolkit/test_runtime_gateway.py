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

import pytest

from agentkit.sdk.runtime.gateway import (
    normalize_runtime_gateway_mode,
    runtime_gateway_binding_changed,
    validate_runtime_gateway_create_config,
)


def test_normalize_runtime_gateway_mode_values():
    assert normalize_runtime_gateway_mode(None) is None
    assert normalize_runtime_gateway_mode("") is None
    assert normalize_runtime_gateway_mode("shared") == "Shared"
    assert normalize_runtime_gateway_mode(" Exclusive ") == "Exclusive"

    with pytest.raises(ValueError, match="Shared or Exclusive"):
        normalize_runtime_gateway_mode("dedicated")


def test_validate_runtime_gateway_create_config():
    validate_runtime_gateway_create_config(
        gateway_mode="Exclusive",
        gateway_instance_id="g-1",
    )

    with pytest.raises(ValueError, match="gateway_instance_id is required"):
        validate_runtime_gateway_create_config(
            gateway_mode="Exclusive",
            gateway_instance_id=None,
        )

    with pytest.raises(ValueError, match="network cannot be used"):
        validate_runtime_gateway_create_config(
            gateway_mode="Exclusive",
            gateway_instance_id="g-1",
            has_network_configuration=True,
        )

    with pytest.raises(ValueError, match="only valid when gateway_mode is Exclusive"):
        validate_runtime_gateway_create_config(
            gateway_mode="Shared",
            gateway_instance_id="g-1",
        )


def test_runtime_gateway_binding_changed():
    assert not runtime_gateway_binding_changed(
        desired_mode=None,
        desired_instance_id=None,
        current_mode=None,
        current_instance_id=None,
    )
    assert runtime_gateway_binding_changed(
        desired_mode="Exclusive",
        desired_instance_id="g-1",
        current_mode="Shared",
        current_instance_id=None,
    )
    assert runtime_gateway_binding_changed(
        desired_mode="Exclusive",
        desired_instance_id="g-2",
        current_mode="Exclusive",
        current_instance_id="g-1",
    )
