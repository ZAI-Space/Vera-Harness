"""Verify CLI selection and real filesystem, network and process boundaries."""

import os
import subprocess
import time

import pytest
import yaml

from minisweagent.environments.sandbox import SandboxConfig, SandboxMode, _bubblewrap, _docker, open_runtime
from tests.run.test_cli_integration import strip_ansi_codes
from tests.run.test_skill_tools import run_cli


def test_cli_auto_requires_a_real_sandbox_and_allows_explicit_local(tmp_path):
    missing_runtime = {
        "MSWEA_DOCKER_EXECUTABLE": str(tmp_path / "missing-docker"),
        "MSWEA_BUBBLEWRAP_EXECUTABLE": str(tmp_path / "missing-bwrap"),
    }
    config = tmp_path / "test.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "model": {
                    "model_class": "deterministic",
                    "model_name": "fixture",
                    "outputs": [
                        {
                            "role": "assistant",
                            "content": "Complete",
                            "extra": {"actions": [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}]},
                        }
                    ],
                },
                "agent": {"agent_class": "default", "system_template": "Use Bash.", "instance_template": "{{task}}"},
            }
        ),
        encoding="utf-8",
    )
    arguments = ("-c", str(config), "-t", "Check execution", "-o", str(tmp_path / "trajectory.json"))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(tmp_path, "minisweagent", *arguments, "--sandbox", "auto", **missing_runtime)
    error = strip_ansi_codes(failure.value.stderr)
    assert "unavailable" in error
    assert "--sandbox local" in error
    assert not (tmp_path / "trajectory.json").exists()

    result = run_cli(tmp_path, "minisweagent", *arguments, "--sandbox", "local", **missing_runtime)
    assert "Execution mode: local (host access)" in result.stdout
    assert (tmp_path / "trajectory.json").is_file()

    if _docker(SandboxConfig()) is not None:
        result = run_cli(tmp_path, "minisweagent", *arguments, "--sandbox", "docker")
        assert "Execution mode: docker" in result.stdout
    if _bubblewrap() is not None:
        result = run_cli(
            tmp_path,
            "minisweagent",
            *arguments,
            "--sandbox",
            "auto",
            MSWEA_DOCKER_EXECUTABLE=missing_runtime["MSWEA_DOCKER_EXECUTABLE"],
        )
        assert "Execution mode: bubblewrap" in result.stdout


def test_cli_rejects_unapproved_external_tools_before_starting_runtime(tmp_path):
    config = tmp_path / "test.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "model": {"model_class": "deterministic", "model_name": "fixture", "outputs": []},
                "sandbox": {"mode": "auto", "workspace": "missing-workspace"},
                "web": {"search_provider": "searxng"},
                "mcp_servers": {
                    "local-docs": {"command": "missing-process"},
                    "remote-api": {"url": "https://example.org/mcp"},
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(tmp_path, "minisweagent", "-c", str(config), "-t", "Check authorization")
    error = failure.value.stderr
    for field in ("sandbox.host_mcp_servers", "sandbox.remote_mcp_servers", "sandbox.allow_web_tools"):
        assert field in error
    assert "missing-workspace" not in error
    settings = yaml.safe_load(config.read_text(encoding="utf-8"))
    settings["sandbox"].update(host_mcp_servers=["local-docs"], remote_mcp_servers=["remote-api"], allow_web_tools=True)
    config.write_text(yaml.safe_dump(settings), encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_cli(tmp_path, "minisweagent", "-c", str(config), "-t", "Check authorization")
    assert "Sandbox workspace is not a directory" in failure.value.stderr


@pytest.fixture(params=[SandboxMode.DOCKER, SandboxMode.BUBBLEWRAP])
def isolated_mode(request):
    mode = request.param
    if mode == SandboxMode.DOCKER and _docker(SandboxConfig()) is None:
        pytest.skip("Local Linux Docker engine or cached Python image unavailable")
    if mode == SandboxMode.BUBBLEWRAP and _bubblewrap() is None:
        pytest.skip("Bubblewrap or working Linux namespaces unavailable")
    return mode


def test_workspace_read_only_credentials_and_shell_network(tmp_path, isolated_mode):
    workspace = tmp_path / "project with spaces"
    workspace.mkdir()
    (workspace / "inside.txt").write_text("VISIBLE", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("PRIVATE", encoding="utf-8")
    token = "MSWEA_SANDBOX_TEST_SECRET"
    previous = os.environ.get(token)
    os.environ[token] = "not-for-the-shell"
    try:
        with open_runtime(SandboxConfig(mode=isolated_mode, workspace=workspace, workspace_access="read-only"), {}) as (
            env,
            mode,
        ):
            assert mode == isolated_mode.value
            result = env.execute(
                {"command": 'cat inside.txt && test ! -e ../outside.txt && test -z "$MSWEA_SANDBOX_TEST_SECRET"'}
            )
            assert result["returncode"] == 0, result
            assert result["output"] == "VISIBLE"
            assert env.execute({"command": "touch forbidden.txt"})["returncode"] != 0
            result = env.execute(
                {
                    "command": "python3 -c 'import socket; s=socket.socket(); s.settimeout(1); s.connect((\"192.0.2.1\", 9))'"
                }
            )
            assert "Network is unreachable" in result["output"]
    finally:
        if previous is None:
            del os.environ[token]
        else:
            os.environ[token] = previous
    assert not (workspace / "forbidden.txt").exists()


def test_timeout_terminates_workspace_processes(tmp_path, isolated_mode):
    config = SandboxConfig(mode=isolated_mode, workspace=tmp_path, timeout=1)
    with open_runtime(config, {}) as (env, _):
        assert env.execute({"command": "printf allowed > before.txt"})["returncode"] == 0
        container = env.container_id if isolated_mode == SandboxMode.DOCKER else None
        result = env.execute({"command": "(sleep 2; printf leaked > after.txt) & sleep 4"})
        assert result["extra"]["exception_type"] == "TimeoutExpired"
        if container is not None:
            assert env.container_id is None
            inspection = subprocess.run(
                [env.config.executable, "container", "inspect", container], capture_output=True, timeout=5
            )
            assert "no such" in inspection.stderr.decode().lower()
        time.sleep(2.1)
    assert (tmp_path / "before.txt").read_text(encoding="utf-8") == "allowed"
    assert not (tmp_path / "after.txt").exists()
