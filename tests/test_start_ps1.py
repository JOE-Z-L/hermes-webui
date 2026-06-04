from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
START_PS1 = REPO_ROOT / "start.ps1"


def _powershell() -> str | None:
    for candidate in ("pwsh", "powershell"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _write_fake_python(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import pathlib
            import sys

            capture = pathlib.Path(os.environ["FAKE_CAPTURE"])
            payload = {
                "argv": sys.argv,
                "env": {
                    "HERMES_HOME": os.environ.get("HERMES_HOME"),
                    "HERMES_CONFIG_PATH": os.environ.get("HERMES_CONFIG_PATH"),
                    "HERMES_WEBUI_STATE_DIR": os.environ.get("HERMES_WEBUI_STATE_DIR"),
                    "HERMES_WEBUI_AGENT_DIR": os.environ.get("HERMES_WEBUI_AGENT_DIR"),
                    "HERMES_WEBUI_PORT": os.environ.get("HERMES_WEBUI_PORT"),
                },
            }
            capture.write_text(json.dumps(payload), encoding="utf-8")
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_fake_python_launcher(tmp_path: Path) -> Path:
    script = tmp_path / "fake-python.py"
    launcher = tmp_path / "fake-python.cmd"
    _write_fake_python(script)
    launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
        encoding="utf-8",
    )
    return launcher


@pytest.mark.skipif(os.name != "nt", reason="start.ps1 launcher regression is Windows-specific")
def test_start_ps1_sets_config_path_from_isolated_hermes_home(tmp_path):
    pwsh = _powershell()
    if not pwsh:
        pytest.skip("PowerShell is not available")

    fake_python = _write_fake_python_launcher(tmp_path)
    capture = tmp_path / "capture.json"
    agent_dir = tmp_path / "agent"
    hermes_home = tmp_path / "isolated-home"
    state_dir = tmp_path / "isolated-state"

    (agent_dir / "hermes_cli").mkdir(parents=True)

    env = os.environ.copy()
    for key in list(env):
        if key.startswith("HERMES_"):
            env.pop(key, None)
    env.update(
        {
            "FAKE_CAPTURE": str(capture),
            "HERMES_WEBUI_PYTHON": str(fake_python),
            "HERMES_WEBUI_AGENT_DIR": str(agent_dir),
            "HERMES_HOME": str(hermes_home),
            "HERMES_WEBUI_STATE_DIR": str(state_dir),
        }
    )

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(START_PS1),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(capture.read_text(encoding="utf-8"))
    assert payload["env"]["HERMES_HOME"] == str(hermes_home)
    assert payload["env"]["HERMES_CONFIG_PATH"] == str(hermes_home / "config.yaml")
    assert payload["env"]["HERMES_WEBUI_STATE_DIR"] == str(state_dir)
    assert payload["argv"][1].endswith("server.py")


@pytest.mark.skipif(os.name != "nt", reason="start.ps1 launcher regression is Windows-specific")
def test_start_ps1_preserves_explicit_config_path_override(tmp_path):
    pwsh = _powershell()
    if not pwsh:
        pytest.skip("PowerShell is not available")

    fake_python = _write_fake_python_launcher(tmp_path)
    capture = tmp_path / "capture.json"
    agent_dir = tmp_path / "agent"
    hermes_home = tmp_path / "isolated-home"
    explicit_config = tmp_path / "custom-config.yaml"

    (agent_dir / "hermes_cli").mkdir(parents=True)

    env = os.environ.copy()
    for key in list(env):
        if key.startswith("HERMES_"):
            env.pop(key, None)
    env.update(
        {
            "FAKE_CAPTURE": str(capture),
            "HERMES_WEBUI_PYTHON": str(fake_python),
            "HERMES_WEBUI_AGENT_DIR": str(agent_dir),
            "HERMES_HOME": str(hermes_home),
            "HERMES_CONFIG_PATH": str(explicit_config),
        }
    )

    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(START_PS1),
            "-Port",
            "8899",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(capture.read_text(encoding="utf-8"))
    assert payload["env"]["HERMES_CONFIG_PATH"] == str(explicit_config)
    assert payload["env"]["HERMES_WEBUI_PORT"] == "8899"
