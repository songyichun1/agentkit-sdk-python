from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "packages" / "agentkit-harness-sidecar-integration"


def _build_wheel(source: Path, destination: Path) -> Path:
    destination.mkdir()
    command = (
        "from setuptools.build_meta import build_wheel; "
        "import sys; print(build_wheel(sys.argv[1]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command, str(destination)],
        cwd=source,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    wheels = list(destination.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def _copy_sdk_source(destination: Path) -> None:
    destination.mkdir()
    shutil.copytree(REPOSITORY_ROOT / "agentkit", destination / "agentkit")
    for filename in ("LICENSE", "MANIFEST.in", "README.md", "pyproject.toml"):
        shutil.copy2(REPOSITORY_ROOT / filename, destination / filename)


def _metadata(wheel: Path) -> tuple[list[str], str, str]:
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        entry_points_name = next(
            (name for name in names if name.endswith(".dist-info/entry_points.txt")),
            None,
        )
        metadata = archive.read(metadata_name).decode("utf-8")
        entry_points = (
            archive.read(entry_points_name).decode("utf-8") if entry_points_name else ""
        )
    return names, metadata, entry_points


def _probe_installation(site_packages: Path, *, plugin_expected: bool) -> None:
    script = """
import importlib.util

spec = importlib.util.find_spec("agentkit.extensions.harness_sidecar")
assert (spec is not None) is PLUGIN_EXPECTED
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(site_packages)
    completed = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            f"PLUGIN_EXPECTED = {plugin_expected!r}\n{script}",
        ],
        cwd=site_packages,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, (completed.stdout + completed.stderr)[-4000:]


def test_built_wheels_preserve_optional_sidecar_boundary(tmp_path: Path) -> None:
    sdk_source = tmp_path / "sdk-source"
    plugin_source = tmp_path / "plugin-source"
    _copy_sdk_source(sdk_source)
    shutil.copytree(PLUGIN_ROOT, plugin_source)

    sdk_wheel = _build_wheel(sdk_source, tmp_path / "sdk-dist")
    plugin_wheel = _build_wheel(plugin_source, tmp_path / "plugin-dist")
    sdk_names, sdk_metadata, sdk_entry_points = _metadata(sdk_wheel)
    plugin_names, plugin_metadata, plugin_entry_points = _metadata(plugin_wheel)

    module_prefix = "agentkit/extensions/harness_sidecar/"
    assert not any(name.startswith(module_prefix) for name in sdk_names)
    assert any(name.startswith(module_prefix) for name in plugin_names)
    assert "agentkit-harness-sidecar-integration" in sdk_metadata
    assert "agentkit.cli_plugins" not in sdk_entry_points
    assert "[agentkit.cli_plugins]" in plugin_entry_points
    assert "harness = agentkit.extensions.harness_sidecar.cli:harness_app" in (
        plugin_entry_points
    )
    public_metadata = f"{sdk_metadata}\n{plugin_metadata}".lower().replace("_", "-")
    assert "bytedance-agentkit-harness-sidecar" not in public_metadata

    base_site = tmp_path / "base-site"
    base_site.mkdir()
    with ZipFile(sdk_wheel) as archive:
        archive.extractall(base_site)
    _probe_installation(base_site, plugin_expected=False)

    extra_site = tmp_path / "extra-site"
    shutil.copytree(base_site, extra_site)
    with ZipFile(plugin_wheel) as archive:
        archive.extractall(extra_site)
    _probe_installation(extra_site, plugin_expected=True)
