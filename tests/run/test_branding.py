"""Verify installed VERA identity, real command execution and legacy settings at process boundaries."""

import json
import os
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

import yaml


def _environment(root: Path) -> dict:
    """Create an isolated config environment without copying local provider credentials into artifacts."""
    environment = {name: value for name, value in os.environ.items() if not name.startswith(("MSWEA_", "VERA_"))}
    return environment | {"VERA_GLOBAL_CONFIG_DIR": str(root), "VERA_CONFIGURED": "true", "PYTHONUTF8": "1"}


def test_installed_vera_and_legacy_cli_execute_and_emit_current_namespace(tmp_path):
    config = tmp_path / "task.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "agent": {
                    "agent_class": "interactive",
                    "mode": "yolo",
                    "confirm_exit": False,
                    "system_template": "Use Bash",
                    "instance_template": "{{task}}",
                    "cost_limit": 1,
                },
                "model": {
                    "model_name": "fixture",
                    "model_class": "deterministic",
                    "cost_per_call": 0,
                    "outputs": [
                        {
                            "role": "assistant",
                            "content": "Run the command",
                            "extra": {
                                "actions": [
                                    {
                                        "command": "printf actual-vera-output > artifact.txt; echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo vera-ready"
                                    }
                                ]
                            },
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    assert distribution("vera-harness").metadata["Name"] == "vera-harness"
    for entry in ("vera", "mini"):
        output = tmp_path / f"{entry}.traj.json"
        result = subprocess.run(
            [entry, "-c", str(config), "-t", "Verify the renamed runtime", "-o", str(output), "--exit-immediately"],
            cwd=tmp_path,
            env=_environment(tmp_path / "settings"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            "VERA" in result.stdout and "mini-swe-agent" not in result.stdout and "migration guide" not in result.stdout
        )
        trajectory = json.loads(output.read_text(encoding="utf-8"))
        assert trajectory["info"]["config"]["agent_type"].startswith("vera.")
        assert "vera_version" in trajectory["info"] and "mini_version" not in trajectory["info"]
        assert trajectory["trajectory_format"] == "vera-1.1"
        assert trajectory["info"]["submission"] == "vera-ready\n"
        assert (tmp_path / "artifact.txt").read_text() == "actual-vera-output"


def test_legacy_environment_and_builtin_names_preserve_user_settings_with_new_precedence(tmp_path):
    old, current = tmp_path / "old", tmp_path / "current"
    old.mkdir()
    (old / ".env").write_text("MSWEA_MODEL_NAME=legacy-model\nMSWEA_CONFIGURED=true\n", encoding="utf-8")
    probe = (
        "import json,os; from vera import global_config_dir; from vera.config import get_config_path; "
        "print(json.dumps([str(global_config_dir),os.getenv('VERA_MODEL_NAME'),os.getenv('VERA_CONFIGURED'),"
        "get_config_path('mini.yaml').name,get_config_path('mini_textbased.yaml').name]))"
    )
    environment = _environment(old)
    environment.pop("VERA_GLOBAL_CONFIG_DIR")
    environment.pop("VERA_CONFIGURED")
    environment.update(MSWEA_GLOBAL_CONFIG_DIR=str(old), MSWEA_SILENT_STARTUP="1")
    result = subprocess.run([sys.executable, "-c", probe], env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [str(old), "legacy-model", "true", "vera.yaml", "vera_textbased.yaml"]
    environment.update(
        VERA_GLOBAL_CONFIG_DIR=str(current), VERA_MODEL_NAME="explicit-new-model", VERA_CONFIGURED="true"
    )
    result = subprocess.run([sys.executable, "-c", probe], env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[:3] == [str(current), "explicit-new-model", "true"]
    assert (old / ".env").read_text().startswith("MSWEA_MODEL_NAME=legacy-model")


def test_module_and_utilities_help_use_vera_and_new_default_config(tmp_path):
    environment = _environment(tmp_path / "settings")
    for command in (
        [sys.executable, "-m", "vera", "--help"],
        ["vera-extra", "--help"],
        ["vera-extra", "mcp", "--help"],
        ["vera-extra", "config", "--help"],
    ):
        result = subprocess.run(command, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=20)
        assert result.returncode == 0, result.stderr
        assert "VERA" in result.stdout or "vera-extra" in result.stdout
        assert "mini-swe-agent.com" not in result.stdout
    from vera.run.cli import DEFAULT_CONFIG_FILE

    assert DEFAULT_CONFIG_FILE.name == "vera.yaml"
