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

"""Discover optional AgentKit CLI plugins without importing them from core."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any

import typer

CLI_PLUGIN_GROUP = "agentkit.cli_plugins"


def load_cli_plugins(
    root: typer.Typer,
    *,
    plugins: Iterable[EntryPoint] | None = None,
) -> None:
    """Register installed CLI plugins; an empty environment is a no-op."""

    discovered = (
        entry_points(group=CLI_PLUGIN_GROUP) if plugins is None else list(plugins)
    )
    for entry_point in sorted(discovered, key=lambda item: item.name):
        try:
            plugin: Any = entry_point.load()
        except Exception as error:
            _warn_plugin_failure(entry_point.name, "load", error)
            continue

        try:
            if isinstance(plugin, typer.Typer):
                root.add_typer(plugin, name=entry_point.name)
                continue
            if callable(plugin):
                plugin(root)
                continue
            typer.echo(
                "Warning: ignoring AgentKit CLI plugin "
                f"{entry_point.name!r}: expected a Typer or callable, "
                f"got {type(plugin).__name__}.",
                err=True,
            )
        except Exception as error:
            _warn_plugin_failure(entry_point.name, "registration", error)


def _warn_plugin_failure(name: str, stage: str, error: Exception) -> None:
    """Report an isolated plugin failure without leaking exception details."""

    typer.echo(
        f"Warning: AgentKit CLI plugin {name!r} failed during {stage} "
        f"({type(error).__name__}); continuing without it.",
        err=True,
    )


__all__ = ["CLI_PLUGIN_GROUP", "load_cli_plugins"]
