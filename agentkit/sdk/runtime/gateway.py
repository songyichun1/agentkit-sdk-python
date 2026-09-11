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

from typing import Any, Optional

RUNTIME_GATEWAY_MODES = {"Shared", "Exclusive"}


def normalize_runtime_gateway_mode(
    value: Any,
    label: str = "runtime.gateway_mode",
) -> Optional[str]:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be Shared or Exclusive.")

    normalized = value.strip().lower()
    if normalized == "shared":
        return "Shared"
    if normalized == "exclusive":
        return "Exclusive"
    raise ValueError(f"{label} must be Shared or Exclusive.")


def effective_runtime_gateway_mode(mode: Optional[str]) -> str:
    return str(mode).strip() if mode and str(mode).strip() else "Shared"


def validate_runtime_gateway_create_config(
    *,
    gateway_mode: Optional[str],
    gateway_instance_id: Optional[str],
    has_network_configuration: bool = False,
    label: str = "runtime",
) -> None:
    mode = (
        normalize_runtime_gateway_mode(gateway_mode, f"{label}.gateway_mode")
        or "Shared"
    )
    gateway_instance_id = (gateway_instance_id or "").strip()

    if mode == "Exclusive":
        if not gateway_instance_id:
            raise ValueError(
                f"{label}.gateway_instance_id is required when gateway_mode is Exclusive."
            )
        if has_network_configuration:
            raise ValueError(
                f"{label}.network cannot be used when gateway_mode is Exclusive; "
                "the Runtime follows the selected gateway instance network."
            )
        return

    if gateway_instance_id:
        raise ValueError(
            f"{label}.gateway_instance_id is only valid when gateway_mode is Exclusive."
        )


def runtime_gateway_binding_changed(
    *,
    desired_mode: Optional[str],
    desired_instance_id: Optional[str],
    current_mode: Optional[str],
    current_instance_id: Optional[str],
) -> bool:
    desired_mode = effective_runtime_gateway_mode(desired_mode)
    current_mode = effective_runtime_gateway_mode(current_mode)

    if desired_mode not in RUNTIME_GATEWAY_MODES or current_mode not in RUNTIME_GATEWAY_MODES:
        return desired_mode != current_mode
    if desired_mode != current_mode:
        return True
    if desired_mode != "Exclusive":
        return False
    return (desired_instance_id or "").strip() != (current_instance_id or "").strip()
