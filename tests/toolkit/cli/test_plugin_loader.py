from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from agentkit.toolkit.cli.plugin_loader import load_cli_plugins


@dataclass(frozen=True)
class _EntryPoint:
    name: str
    value: Any
    load_error: Exception | None = None

    def load(self) -> Any:
        if self.load_error is not None:
            raise self.load_error
        return self.value


def test_empty_plugin_set_does_not_change_core_cli() -> None:
    root = typer.Typer()

    @root.command("core")
    def core() -> None:
        typer.echo("core-ok")

    load_cli_plugins(root, plugins=[])

    result = CliRunner().invoke(root, ["--help"])
    assert result.exit_code == 0
    assert "harness" not in result.output


def test_installed_typer_plugin_is_registered_by_entry_point_name() -> None:
    root = typer.Typer()
    plugin = typer.Typer()

    @plugin.command("status")
    def status() -> None:
        typer.echo("plugin-ok")

    load_cli_plugins(root, plugins=[_EntryPoint("harness", plugin)])

    result = CliRunner().invoke(root, ["harness", "status"])
    assert result.exit_code == 0
    assert result.output.strip() == "plugin-ok"


def test_plugin_load_failure_warns_and_continues(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = typer.Typer()
    plugin = typer.Typer()

    @plugin.command("status")
    def status() -> None:
        typer.echo("healthy-ok")

    load_cli_plugins(
        root,
        plugins=[
            _EntryPoint("broken", None, RuntimeError("private details")),
            _EntryPoint("healthy", plugin),
        ],
    )

    warning = capsys.readouterr().err
    assert "plugin 'broken' failed during load (RuntimeError)" in warning
    assert "private details" not in warning
    result = CliRunner().invoke(root, ["healthy", "status"])
    assert result.exit_code == 0
    assert result.output.strip() == "healthy-ok"


def test_plugin_registration_failure_warns_and_continues(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = typer.Typer()
    plugin = typer.Typer()

    def broken_registration(_root: typer.Typer) -> None:
        raise ValueError("private details")

    @plugin.command("status")
    def status() -> None:
        typer.echo("healthy-ok")

    load_cli_plugins(
        root,
        plugins=[
            _EntryPoint("broken", broken_registration),
            _EntryPoint("healthy", plugin),
        ],
    )

    warning = capsys.readouterr().err
    assert "plugin 'broken' failed during registration (ValueError)" in warning
    assert "private details" not in warning
    result = CliRunner().invoke(root, ["healthy", "status"])
    assert result.exit_code == 0
    assert result.output.strip() == "healthy-ok"


def test_invalid_plugin_contract_warns_without_breaking_core_cli(
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = typer.Typer()

    @root.command("core")
    def core() -> None:
        typer.echo("core-ok")

    @root.command("other")
    def other() -> None:
        typer.echo("other-ok")

    load_cli_plugins(root, plugins=[_EntryPoint("invalid", object())])

    warning = capsys.readouterr().err
    assert "plugin 'invalid'" in warning
    assert "expected a Typer or callable, got object" in warning
    result = CliRunner().invoke(root, ["core"])
    assert result.exit_code == 0
    assert result.output.strip() == "core-ok"
