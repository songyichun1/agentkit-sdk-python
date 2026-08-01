# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Fail-closed loader for AgentKit's bundled Runtime Identity module."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType

_INSTALL_HINT = (
    "The bundled Agent Identity Runtime module is missing from this AgentKit "
    "installation. Reinstall a matching 'agentkit-sdk-python' wheel."
)


def require_identity_runtime() -> ModuleType:
    try:
        return import_module("agentkit_identity")
    except ModuleNotFoundError as exc:
        if exc.name != "agentkit_identity":
            raise
        raise RuntimeError(_INSTALL_HINT) from exc
