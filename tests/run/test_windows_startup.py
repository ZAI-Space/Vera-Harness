"""Exercise both startup entries against actual Git Bash without model API calls."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from vera.models.test_models import make_output
from vera.utils.windows_bash import find_git_bash

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows startup entry points")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("entry", ["cmd", "powershell", "bash"])
def test_startup_forwards_quoted_arguments_and_runs_agent(tmp_path, entry):
    task = "中文 task with spaces; literal $value & quotes"
    config_path = tmp_path / "配置 with spaces.yaml"
    trajectory_path = tmp_path / f"{entry} trajectory.json"
    config_path.write_text(
        yaml.safe_dump(
            {
                "agent": {
                    "agent_class": "default",
                    "system_template": "Use bash.",
                    "instance_template": "{{task}}",
                    "cost_limit": 0,
                },
                "model": {
                    "model_name": "deterministic",
                    "model_class": "deterministic",
                    "outputs": [make_output("Finished", [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}])],
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    arguments = ["-c", str(config_path), "-t", task, "-o", str(trajectory_path)]
    if entry == "powershell":
        script = tmp_path / "launch.ps1"
        script.write_text('& "$env:VERA_TEST_PROJECT_ROOT/start.cmd" @args\nexit $LASTEXITCODE\n', encoding="utf-8")
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments]
    elif entry == "cmd":
        command = [os.environ["COMSPEC"], "/d", "/c", str(PROJECT_ROOT / "start.cmd"), *arguments]
    else:
        command = [find_git_bash(), "--noprofile", "--norc", str(PROJECT_ROOT / "scripts/start.sh"), *arguments]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=os.environ
        | {
            "VERA_CONFIGURED": "true",
            "VERA_GLOBAL_CONFIG_DIR": str(tmp_path / "config"),
            "VERA_TEST_PROJECT_ROOT": str(PROJECT_ROOT),
        },
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
    assert trajectory["messages"][1]["content"] == task
    assert trajectory["info"]["exit_status"] == "Submitted"


def test_explicit_missing_bash_fails_before_download(tmp_path):
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src/vera/utils/windows_bash.py"), "--help"],
        env=os.environ | {"VERA_BASH_PATH": str(tmp_path / "missing/bash.exe")},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "does not exist" in result.stderr
    assert "Downloading" not in result.stdout


@pytest.mark.parametrize("entry", ["cmd", "bash"])
def test_startup_preserves_cli_error_exit_code(entry):
    command = (
        [os.environ["COMSPEC"], "/d", "/c", str(PROJECT_ROOT / "start.cmd"), "--unknown-option"]
        if entry == "cmd"
        else [find_git_bash(), str(PROJECT_ROOT / "scripts/start.sh"), "--unknown-option"]
    )
    result = subprocess.run(command, capture_output=True, timeout=30)
    assert result.returncode == 2
