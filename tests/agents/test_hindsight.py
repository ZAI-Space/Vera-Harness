"""Exercise the memory CLI and agent against a local Hindsight HTTP contract fixture."""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from minisweagent.agents.hindsight import HindsightAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.memory.hindsight import HindsightMemory
from minisweagent.models.test_models import DeterministicModel, make_output


@pytest.fixture
def memory_service():
    bank_path = "/v1/default/banks/test-project/memories"
    shared_path = "/v1/default/banks/test-shared/memories/recall"
    notes = []
    requests = []

    class MemoryHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            if self.headers.get("Authorization") != "Bearer fixture-key":
                self._send(401, {})
            elif self.path == bank_path:
                notes.extend(item["content"] for item in body["items"])
                self._send(200, {"success": True})
            elif self.path == bank_path + "/recall" and body["query"] == "Simulate service outage":
                self._send(503, {})
            elif self.path == bank_path + "/recall":
                records = [{"text": note} for note in notes]
                if body["query"] == "Which package manager?":
                    old = {"id": "old", "type": "experience", "text": "Previously used npm."}
                    current = {
                        "id": "current",
                        "type": "observation",
                        "text": "Now uses pnpm.",
                        "source_fact_ids": ["old"],
                    }
                    records = [current] if body["prefer_observations"] else [old]
                self._send(200, {"results": records})
            elif self.path == shared_path:
                self._send(200, {"results": [{"text": "Shared guidance", "id": "shared-note", "type": "world"}]})
            elif self.path == "/v1/default/banks/test-project/reflect":
                self._send(200, {"text": "Now uses pnpm.", "based_on": {"memories": [{"id": "current"}]}})
            else:
                self._send(404, {})

        def do_PATCH(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            if self.path == bank_path + "/old" and self.headers.get("Authorization") == "Bearer fixture-key":
                self._send(200, {"state": body["state"]})
            else:
                self._send(404, {})

        def _send(self, status, data):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

    with ThreadingHTTPServer(("127.0.0.1", 0), MemoryHandler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            worker.join(timeout=5)


def _finish():
    return make_output("Finish", [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}])


def test_retain_and_recall_across_cli_processes(memory_service, tmp_path):
    endpoint, requests = memory_service
    key_file = tmp_path / "hindsight-key"
    key_file.write_text("fixture-key", encoding="utf-8")
    environ = os.environ | {
        "HINDSIGHT_BASE_URL": endpoint,
        "HINDSIGHT_BANK_ID": "test-project",
        "HINDSIGHT_API_KEY_FILE": str(key_file),
        "MSWEA_CONFIGURED": "true",
        "MSWEA_GLOBAL_CONFIG_DIR": str(tmp_path / "config"),
        "MSWEA_SILENT_STARTUP": "1",
    }
    note = "Run unit tests with pytest. {{ template_text }}"
    memory_cli = [sys.executable, "-m", "minisweagent.run.utilities.mini_extra", "memory"]
    subprocess.run([*memory_cli, "retain", note], env=environ, check=True, capture_output=True, timeout=30)
    recalled = subprocess.run(
        [*memory_cli, "recall", "How do I run tests?"], env=environ, check=True, capture_output=True, timeout=30
    )
    assert note in recalled.stdout.decode("utf-8")

    config = tmp_path / "memory-test.yaml"
    config.write_text(
        json.dumps(
            {
                "agent": {
                    "system_template": "Follow the current task.",
                    "instance_template": "{{ task }}",
                    "mode": "confirm",
                    "whitelist_actions": ["^echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT$"],
                    "confirm_exit": False,
                },
                "model": {"model_name": "deterministic", "model_class": "deterministic", "outputs": [_finish()]},
            }
        ),
        encoding="utf-8",
    )
    trajectory = tmp_path / "memory.traj.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "minisweagent",
            "--agent-class",
            "hindsight_interactive",
            "-c",
            str(config),
            "-o",
            str(trajectory),
            "-t",
            "Verify project tests",
        ],
        env=environ,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    saved = trajectory.read_text(encoding="utf-8")
    run = json.loads(saved)
    assert run["info"]["exit_status"] == "Submitted"
    assert run["messages"][0]["content"] == "Follow the current task."
    assert note in run["messages"][1]["content"]
    assert "fixture-key" not in saved
    assert [body.get("query") for _, body in requests] == [None, "How do I run tests?", "Verify project tests"]
    assert all("/banks/test-project/" in path for path, _ in requests)


def test_failed_recall_does_not_reuse_previous_run_memory(memory_service, caplog):
    endpoint, requests = memory_service
    memory = HindsightMemory(endpoint, "test-project", api_key="fixture-key")
    memory.retain("project memory " * 400)
    agent = HindsightAgent(
        DeterministicModel(outputs=[_finish(), _finish()]),
        LocalEnvironment(),
        system_template="Use Bash.",
        instance_template="{{ task }}",
        memory=memory,
    )
    assert agent.run("Find memory")["exit_status"] == "Submitted"
    assert "project memory" in agent.messages[1]["content"]
    assert len(agent.messages[1]["content"]) < 4500
    assert agent.run("Simulate service outage")["exit_status"] == "Submitted"
    assert agent.messages[1]["content"] == "Simulate service outage"
    assert "Hindsight recall returned HTTP 503" in caplog.text
    assert len(requests) == 3


def test_conflict_modes_and_reversible_curation(memory_service):
    endpoint, requests = memory_service
    memory = HindsightMemory(endpoint, "test-project", api_key="fixture-key")
    context = {}
    for mode in ("disabled", "facts", "observations", "reflect"):
        agent = HindsightAgent(
            DeterministicModel(outputs=[_finish()]),
            LocalEnvironment(),
            system_template="Use Bash.",
            instance_template="{{ task }}",
            memory=memory,
            memory_mode=mode,
        )
        assert agent.run("Which package manager?")["exit_status"] == "Submitted"
        context[mode] = agent.messages[1]["content"]
    assert context["disabled"] == "Which package manager?"
    assert "Previously used npm." in context["facts"]
    assert "Now uses pnpm." in context["observations"]
    assert "Previously used npm." not in context["observations"]
    assert '"source_fact_ids": ["old"]' in context["observations"]
    assert '"source_fact_ids": ["current"]' in context["reflect"]
    assert [body.get("prefer_observations") for _, body in requests] == [False, True, None]
    memory.set_validity("old", is_valid=False, reason="Replaced by pnpm in the current workspace")
    memory.set_validity("old", is_valid=True)
    assert requests[-2][1] == {"state": "invalidated", "reason": "Replaced by pnpm in the current workspace"}
    assert requests[-1][1] == {"state": "valid"}


def test_shared_bank_is_read_only_and_opt_in(memory_service):
    endpoint, requests = memory_service
    agent = HindsightAgent(
        DeterministicModel(outputs=[_finish()]),
        LocalEnvironment(),
        system_template="Use Bash.",
        instance_template="{{ task }}",
        memory=HindsightMemory(endpoint, "test-project", api_key="fixture-key"),
        shared_memory=HindsightMemory(endpoint, "test-shared", api_key="fixture-key"),
    )
    agent.run("Which package manager?")
    assert [path for path, _ in requests] == [
        "/v1/default/banks/test-project/memories/recall",
        "/v1/default/banks/test-shared/memories/recall",
    ]
    message = agent.messages[1]["content"]
    assert '"bank": "test-shared", "scope": "shared"' in message
    assert "Shared guidance" in message
