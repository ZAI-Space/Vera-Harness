"""Verify terminal choices through the assembled runtime, real HTTP, MCP and SQLite."""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
import yaml

from tests.run.test_skill_tools import run_cli, write_skill
from tests.run.test_web_tools import FINISH_CALL, _model_response
from vera.models.openrouter_model import OpenRouterModel
from vera.runtime import open_agent_runtime
from vera.storage import RunStore
from vera.terminal.session import TerminalSession
from vera.tools import ToolError


class TerminalFixtureModel(OpenRouterModel):
    """Use the real HTTP model adapter with an explicitly configured local peer."""

    def __init__(self, api_url, **kwargs):
        super().__init__(**kwargs)
        self._api_url = api_url


@pytest.fixture
def terminal_model():
    """A deterministic HTTP peer using the production model adapter protocol."""
    state = {"requests": [], "actions": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(payload)
            sequence = state["actions"].get(payload["model"], [])
            action = sequence.pop(0) if sequence else FINISH_CALL
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_model_response([action], False)).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            state["url"] = f"http://127.0.0.1:{server.server_port}"
            yield state
        finally:
            server.shutdown()
            thread.join(timeout=5)


def runtime_profile(tmp_path):
    """Build a complete configuration without external credentials or services."""
    return {
        "model": {"model_class": "openrouter", "model_name": "parent"},
        "agent": {
            "agent_class": "interactive",
            "mode": "yolo",
            "confirm_exit": False,
            "system_template": "Use registered tools.",
            "instance_template": "{{task}}",
            "step_limit": 6,
        },
        "plugins": {"directory": str(tmp_path / "plugins")},
        "sandbox": {"mode": "local", "workspace": str(tmp_path)},
    }


def test_readonly_runtime_blocks_parent_child_and_legacy_shell_and_records_completion(tmp_path, terminal_model):
    config = runtime_profile(tmp_path)
    config["model"].update(
        model_class="tests.run.test_terminal_runtime.TerminalFixtureModel", api_url=terminal_model["url"]
    )
    config["permissions"] = {"mode": "read-only"}
    marker = tmp_path / "mcp-started.txt"
    config["mcp_servers"] = {
        "blocked": {
            "command": sys.executable,
            "args": ["-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"],
        }
    }
    config["subagents"] = {
        "roles": {
            "reviewer": {
                "description": "Readonly review",
                "instructions": "Review selected context",
                "tools": ["bash", "mcp_blocked_write"],
            }
        }
    }
    config["subagents"]["roles"]["reviewer"]["model"] = config["model"] | {"model_name": "child"}
    terminal_model["actions"]["child"] = [("subagent_finish", {"summary": "child reviewed"})]
    write_skill(tmp_path / ".agents/skills", "review", "Read-only workflow.")
    terminal_model["actions"]["parent"] = [
        ("bash", {"command": "printf forbidden > forbidden.txt"}),
        ("subagent_run", {"role": "reviewer", "task": "Review only"}),
        ("task_finish", {"summary": "readonly completed"}),
    ]
    with open_agent_runtime(config) as runtime:
        agent = runtime.agent
        agent.model._api_url = terminal_model["url"]
        child = config["subagents"]["roles"]["reviewer"]
        assert child["tools"] == ["bash", "mcp_blocked_write"]  # input not mutated
        assert agent.env.execute({"command": "printf forbidden > forbidden.txt"})["returncode"] == 1
        assert "review" in runtime.skills
        assert '"permissions": "read-only"' in runtime.policy
        with RunStore(tmp_path / "runs.sqlite3").track(
            agent, workspace=tmp_path, runtime_policy=runtime.policy
        ) as record:
            assert agent.run("Readonly project review")["submission"] == "readonly completed"
            run_id = record.id
        assert RunStore(tmp_path / "runs.sqlite3").get_run(run_id)["status"] == "completed"
        assert not {"bash", "mcp_blocked_write"} & {
            item["function"]["name"] for item in agent.tool_registry.definitions()
        }
    assert not marker.exists() and not (tmp_path / "forbidden.txt").exists()
    assert len(terminal_model["requests"]) == 4
    child_request = next(row for row in terminal_model["requests"] if row["model"] == "child")
    assert {tool["function"]["name"] for tool in child_request["tools"]} == {"subagent_finish"}
    assert "Readonly project review" not in json.dumps(child_request)


def test_mcp_selection_removes_delegated_tools_and_closes_real_servers(tmp_path):
    pytest.importorskip("mcp")
    config = runtime_profile(tmp_path)
    config["mcp_servers"] = {
        "fixture": {
            "command": sys.executable,
            "args": [str(Path(__file__).with_name("mcp_fixture.py"))],
            "allow_tools": ["echo"],
        }
    }
    config["subagents"] = {
        "roles": {"reviewer": {"description": "Review", "instructions": "Review", "tools": ["mcp_fixture_echo"]}}
    }
    session = TerminalSession(config, tmp_path)
    session.process("/permissions auto")
    session.process("/mcp fixture")
    with open_agent_runtime(session.runtime_config()) as runtime:
        result = runtime.agent.tool_registry.execute(
            {"tool": "mcp_fixture_echo", "arguments": {"text": "selected MCP"}}
        )
        assert result["returncode"] == 0 and "selected MCP" in result["output"]
    session.process("/mcp none")
    with open_agent_runtime(session.runtime_config()) as runtime:
        assert "mcp_fixture_echo" not in {
            item["function"]["name"] for item in runtime.agent.tool_registry.definitions()
        }
        assert runtime.agent.tool_registry.execute({"tool": "subagents_list", "arguments": {}})["returncode"] == 0
    assert config["subagents"]["roles"]["reviewer"]["tools"] == ["mcp_fixture_echo"]


def test_confirm_policy_rejects_noninteractive_custom_agent(tmp_path):
    config = runtime_profile(tmp_path)
    config["agent"]["agent_class"] = "default"
    config["permissions"] = {"mode": "confirm"}
    with pytest.raises(ToolError, match="interactive agent"):
        with open_agent_runtime(config):
            pytest.fail("Confirmation was silently bypassed")


def test_cli_expands_explicit_file_and_readonly_native_completion(tmp_path, terminal_model):
    (tmp_path / "项目 file.md").write_text("actual file content {{ keep literal }}", encoding="utf-8")
    config = runtime_profile(tmp_path)
    config["model"]["model_class"] = "tests.run.test_web_tools.LocalFixtureModel"
    config["permissions"] = {"mode": "read-only"}
    terminal_model["actions"]["parent"] = [("task_finish", {"summary": "file checked"})]
    profile = tmp_path / "terminal.yaml"
    profile.write_text(yaml.safe_dump(config), encoding="utf-8")
    result = run_cli(
        tmp_path,
        "vera.run.cli",
        "-c",
        str(profile),
        "-t",
        'Read @"项目 file.md"',
        "--exit-immediately",
        "--storage",
        str(tmp_path / "cli.sqlite3"),
        "-o",
        str(tmp_path / "run.json"),
        VERA_TEST_MODEL_URL=terminal_model["url"],
        OPENROUTER_API_KEY="fixture",
    )
    assert "Saved trajectory" in result.stdout
    assert "actual file content {{ keep literal }}" in json.dumps(terminal_model["requests"][0], ensure_ascii=False)
    assert json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))["info"]["exit_status"] == "Submitted"
