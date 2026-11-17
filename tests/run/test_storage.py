"""Verify the persisted CLI history and recovery information after an abrupt process exit."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from minisweagent.storage import RunStore
from tests.run.test_skill_tools import run_cli

RUNS_CLI = "minisweagent.run.utilities.mini_extra"


def _write_config(path, *commands, **agent_config):
    path.write_text(
        yaml.safe_dump(
            {
                "model": {
                    "model_class": "deterministic",
                    "model_name": "fixture",
                    "outputs": [
                        {
                            "role": "assistant",
                            "content": "Execute",
                            "extra": {"actions": [{"command": command, "tool_call_id": "provider-id"}]},
                        }
                        for command in commands
                    ],
                },
                "agent": {
                    "agent_class": "default",
                    "system_template": "Use Bash.",
                    "instance_template": "{{task}}",
                    **agent_config,
                },
            }
        ),
        encoding="utf-8",
    )


def test_cli_lists_independent_runs_and_preserves_default_trajectories(tmp_path):
    database = tmp_path / "run records.sqlite3"
    config = tmp_path / "test.yaml"
    command = "printf storage-payload > recorded.txt"
    config.write_text(
        yaml.safe_dump(
            {
                "model": {
                    "model_class": "deterministic",
                    "model_name": "fixture",
                    "outputs": [
                        {
                            "role": "assistant",
                            "content": "Execute",
                            "extra": {"actions": [{"command": action, "tool_call_id": "provider-id"}]},
                        }
                        for action in [command, "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"]
                    ],
                },
                "agent": {"agent_class": "default", "system_template": "Use Bash.", "instance_template": "{{task}}"},
            }
        ),
        encoding="utf-8",
    )
    for index in range(2):
        result = run_cli(tmp_path, "minisweagent", "-c", str(config), "--storage", str(database), "-t", f"Task {index}")
        assert "Run ID:" in result.stdout

    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(
            tmp_path, "minisweagent", "-c", str(config), "--storage", str(database), "-o", str(database), "-t", "Task"
        )
    assert "need separate paths" in failure.value.stderr

    cli = "minisweagent.run.utilities.mini_extra"
    runs = json.loads(run_cli(tmp_path, cli, "runs", "list", "--db", str(database)).stdout)
    assert len(runs) == 2
    paths = [Path(run["trajectory_path"]) for run in runs]
    assert paths[0] != paths[1]
    assert all(path.is_file() for path in paths)
    result = run_cli(tmp_path, cli, "runs", "show", runs[0]["id"], "--db", str(database)).stdout
    details = json.loads(result)
    assert details["tool_calls"][0]["action"]["command"] == command
    assert details["status"] == "completed"
    assert details["exit_reason"] == "Submitted"
    assert details["model_calls"] == 2
    assert [
        (call["tool"], call["provider_call_id"], call["status"], call["returncode"]) for call in details["tool_calls"]
    ] == [("bash", "provider-id", "returned", 0)] * 2


def test_abrupt_exit_leaves_unknown_receipt(tmp_path):
    database = tmp_path / "crashed.sqlite3"
    marker = tmp_path / "dispatch-reached"
    script = """
import os
import sys
from pathlib import Path
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models import get_model
from minisweagent.storage import RunStore

class ExitDuringDispatch(DefaultAgent):
    def _dispatch_action(self, action):
        Path(sys.argv[2]).touch()
        os._exit(19)

model = get_model(config={"model_class": "deterministic", "model_name": "fixture", "outputs": [{
    "role": "assistant", "content": "dispatch", "extra": {"actions": [{"command": "private command", "tool_call_id": "in-flight"}]},
}]})
agent = ExitDuringDispatch(model, LocalEnvironment(), system_template="Use Bash.", instance_template="{{task}}")
with RunStore(Path(sys.argv[1])).track(agent):
    agent.run("Original task")
"""
    process = subprocess.run([sys.executable, "-c", script, str(database), str(marker)], cwd=tmp_path, timeout=15)
    assert process.returncode == 19
    assert marker.exists()
    store = RunStore(database)
    run = store.get_run(store.list_runs()[0]["id"])
    assert run["status"] == "running"
    assert run["ended_at"] is None
    [receipt] = run["tool_calls"]
    assert receipt["status"] == "unknown"
    assert receipt["provider_call_id"] == "in-flight"
    assert receipt["ended_at"] is None
    assert receipt["action"]["command"] == "private command"
    config = tmp_path / "resume.yaml"
    _write_config(config, "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT")
    arguments = ("-c", str(config), "--storage", str(database), "--resume", run["id"])
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(tmp_path, "minisweagent", *arguments)
    assert "--reconcile" in failure.value.stderr
    assert len(store.list_runs()) == 1
    run_cli(tmp_path, "minisweagent", *arguments, "--reconcile", "The marker exists. Leave it in place.")
    continuation, interrupted = store.list_runs()
    assert continuation["resumed_from"] == interrupted["id"]
    assert continuation["status"] == "completed"
    assert interrupted["status"] == "interrupted"
    messages = json.loads(Path(continuation["trajectory_path"]).read_text(encoding="utf-8"))["messages"]
    assert messages[1]["content"] == "Original task"
    assert "The marker exists" in messages[2]["content"]
    assert len(store.get_run(continuation["id"])["tool_calls"]) == 1
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(tmp_path, "minisweagent", *arguments, "--reconcile", "Verified")
    assert "already has a continuation" in failure.value.stderr


def test_cancel_and_resume_without_replaying_completed_actions(tmp_path):
    database = tmp_path / "runs.sqlite3"
    config = tmp_path / "run.yaml"
    _write_config(config, "printf once >> effect.txt; sleep 8", "printf unexpected > should-not-run")
    trajectory = tmp_path / "cancelled.json"
    arguments = ("-c", str(config), "--storage", str(database))
    env = os.environ | {"MSWEA_CONFIGURED": "true", "MSWEA_GLOBAL_CONFIG_DIR": str(tmp_path / "user-config")}
    process = subprocess.Popen(
        [sys.executable, "-m", "minisweagent", *arguments, "-t", "Original task", "-o", str(trajectory)],
        env=env,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    store = RunStore(database)
    try:
        deadline = time.monotonic() + 15
        while not (tmp_path / "effect.txt").exists():
            if process.poll() is not None:
                _, stderr = process.communicate()
                pytest.fail(stderr.decode(errors="replace"))
            assert time.monotonic() < deadline
            time.sleep(0.05)
        original_id = store.list_runs()[0]["id"]
        with pytest.raises(subprocess.CalledProcessError) as failure:
            run_cli(tmp_path, "minisweagent", *arguments, "--resume", original_id, "--reconcile", "Inspect first.")
        assert "Cannot acquire the lock" in failure.value.stderr
        run_cli(tmp_path, RUNS_CLI, "runs", "cancel", original_id, "--db", str(database))
        _, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr.decode(errors="replace")
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    original = store.get_run(original_id)
    assert original["status"] == "cancelled"
    assert original["cancel_requested_at"]
    assert [call["status"] for call in original["tool_calls"]] == ["returned"]
    assert not (tmp_path / "should-not-run").exists()
    _write_config(config, "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT")
    run_cli(tmp_path, "minisweagent", *arguments, "--resume", original_id)
    [continuation, _] = store.list_runs()
    assert continuation["resumed_from"] == original_id
    assert continuation["status"] == "completed"
    assert (tmp_path / "effect.txt").read_text(encoding="utf-8") == "once"
    messages = json.loads(Path(continuation["trajectory_path"]).read_text(encoding="utf-8"))["messages"]
    assert messages[1]["content"] == "Original task"
    assert any("effect.txt" in str(message) for message in messages)


def test_reading_missing_database_does_not_create_it(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(subprocess.CalledProcessError):
        run_cli(tmp_path, "minisweagent.run.utilities.mini_extra", "runs", "list", "--db", str(missing))
    assert not missing.exists()
