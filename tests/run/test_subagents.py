"""Run delegated roles with real model adapters, Bash, skills and a shared MCP session."""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
import yaml

from tests.run.test_skill_tools import run_cli, write_skill
from tests.run.test_web_tools import FINISH_CALL, _model_response
from vera.agents.interactive import InteractiveAgent
from vera.storage import RunStore


class RejectChildBashAgent(InteractiveAgent):
    """Reject Bash in the shared confirmation path while allowing delegation and parent completion."""

    def _ask_confirmation_or_interrupt(self, commands, *, tool_calls=()):
        if any("child-result.txt" in command for command in commands):
            assert self.config.mode == "confirm"
            self._interrupt("User rejected delegated Bash.", itype="UserRejection")


@pytest.mark.parametrize(("with_mcp", "reject_bash"), [(True, False), (False, False), (False, True)])
def test_cli_delegates_fresh_contexts_with_scoped_runtime(tmp_path, with_mcp, reject_bash):
    if with_mcp:
        pytest.importorskip("mcp")
    skill_root = tmp_path / ".agents" / "skills"
    write_skill(skill_root, "assigned", "USE THIS WORKFLOW")
    write_skill(skill_root, "unassigned", "NEVER INHERIT THIS")
    model_class = "tests.run.test_web_tools.LocalFixtureModel"
    root = {
        "subagents": {
            "roles": {
                "reviewer": {
                    "description": "Review a selected change.",
                    "instructions": "Work independently. Keep this literal {{ secret }}.",
                    "model": {"model_class": model_class, "model_name": "role-model"},
                    "tools": ["bash", "mcp_fixture_echo"] if with_mcp else ["bash"],
                    "skills": ["assigned"],
                },
                "observer": {
                    "description": "Reply without using the workspace.",
                    "instructions": "Summarize only the given facts.",
                },
            }
        }
    }
    if reject_bash:
        root["subagents"]["roles"]["reviewer"]["step_limit"] = 3
    if with_mcp:
        root["mcp_servers"] = {
            "fixture": {"command": sys.executable, "args": [str(Path(__file__).with_name("mcp_fixture.py"))]}
        }
    config = tmp_path / "roles.yaml"
    config.write_text(yaml.safe_dump(root), encoding="utf-8")
    parent_actions = iter(
        [
            ("subagents_list", {}),
            ("subagent_run", {"role": "reviewer", "task": "First child only"}),
            ("subagent_run", {"role": "observer", "task": "Second child only"}),
            FINISH_CALL,
        ]
    )
    child_actions = [
        ("skills_list", {}),
        ("skill_view", {"name": "assigned"}),
        ("bash", {"command": "printf 'shared runtime' > child-result.txt"}),
    ]
    if with_mcp:
        child_actions.append(("mcp_fixture_echo", {"text": "reused MCP session"}))
    child_actions.append(("subagent_finish", {"summary": "First child result"}))
    child_actions_iter = iter(child_actions)
    parent_requests = []
    child_requests = []
    observer_requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            system = payload["messages"][0]["content"]
            if system.startswith("You are the reviewer subagent"):
                child_requests.append(payload)
                action = next(child_actions_iter)
            elif system.startswith("You are the observer subagent"):
                observer_requests.append(payload)
                action = ("subagent_finish", {"summary": "Second child result"})
            else:
                parent_requests.append(payload)
                action = next(parent_actions)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_model_response([action], responses_api=False)).encode())

    trajectory = tmp_path / "parent.json"
    database = tmp_path / "runs.sqlite3"
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            run_cli(
                tmp_path,
                "vera",
                "-c",
                "vera.yaml",
                "-c",
                str(config),
                "-t",
                "PARENT PRIVATE TASK",
                "--model",
                "parent-model",
                "--model-class",
                model_class,
                *(["--agent-class", "tests.run.test_subagents.RejectChildBashAgent"] if reject_bash else ["-y"]),
                "--exit-immediately",
                "--storage",
                str(database),
                "-o",
                str(trajectory),
                VERA_TEST_MODEL_URL=f"http://127.0.0.1:{server.server_port}",
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)

    result_file = tmp_path / "child-result.txt"
    if reject_bash:
        assert not result_file.exists()
        assert "LimitsExceeded" in json.dumps(parent_requests[-1])
    else:
        assert result_file.read_text(encoding="utf-8") == "shared runtime"
        assert "First child result" in json.dumps(parent_requests[-1])
    assert child_requests[0]["model"] == "role-model"
    assert observer_requests[0]["model"] == "parent-model"
    assert child_requests[0]["messages"][1]["content"] == "First child only"
    assert observer_requests[0]["messages"][1]["content"] == "Second child only"
    assert "{{ secret }}" in child_requests[0]["messages"][0]["content"]
    assert [tool["function"]["name"] for tool in observer_requests[0]["tools"]] == ["subagent_finish"]
    assert [tool["function"]["name"] for tool in child_requests[0]["tools"]] == (
        root["subagents"]["roles"]["reviewer"]["tools"] + ["skills_list", "skill_view", "subagent_finish"]
    )
    assert "unassigned" not in json.dumps(child_requests[-1])
    assert "PARENT PRIVATE TASK" not in json.dumps(child_requests)
    assert "USE THIS WORKFLOW" in json.dumps(child_requests[-1])
    if with_mcp:
        assert "reused MCP session" in json.dumps(child_requests[-1])
    assert "Second child result" in json.dumps(parent_requests[-1])
    assert "USE THIS WORKFLOW" not in json.dumps(parent_requests[-1])
    saved = json.loads(trajectory.read_text(encoding="utf-8"))
    assert saved["info"]["exit_status"] == "Submitted"
    assert saved["info"]["model_stats"]["instance_cost"] == pytest.approx(0.01 * (5 + len(child_requests)))
    store = RunStore(database)
    parent = store.get_run(next(row["id"] for row in store.list_runs() if row["parent_id"] is None))
    reviewer, observer = parent["children"]
    assert parent["cost"] == pytest.approx(saved["info"]["model_stats"]["instance_cost"])
    assert [reviewer["role"], observer["role"]] == ["reviewer", "observer"]
    assert {Path(child["trajectory_path"]) for child in parent["children"]} == set(
        (tmp_path / "parent.subagents").glob("*.traj.json")
    )
    assert [call["tool"] for call in parent["tool_calls"]] == ["subagents_list", "subagent_run", "subagent_run", "bash"]
    reviewer = store.get_run(reviewer["id"])
    if reject_bash:
        assert reviewer["exit_reason"] == "LimitsExceeded"
        assert [call["tool"] for call in reviewer["tool_calls"]] == ["skills_list", "skill_view"]
    else:
        assert reviewer["status"] == "completed"
        assert [call["tool"] for call in reviewer["tool_calls"]] == [name for name, _ in child_actions]
