"""Exercise composed runtime behavior through real CLI and message transports.

HTTP services provide deterministic protocol responses, not vendor validation.
Agents, Bash, FastMCP, plugin packages, SDK transports and SQLite run unchanged.
"""

import json
import shutil
import subprocess
import sys
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
import yaml

from tests.agents.test_hindsight import memory_service as memory_service
from tests.run.channel_fixture import feishu_event, feishu_socket, provider_service, weixin_message
from tests.run.test_channels import start_gateway, stop_gateway, wait_for
from tests.run.test_plugins import write_market, write_plugin
from tests.run.test_skill_tools import run_cli, write_skill
from tests.run.test_web_tools import FINISH_CALL, _model_response
from tests.run.test_web_tools import web_service as web_service
from vera.channels.store import ChannelStore
from vera.environments.sandbox import SandboxConfig, _bubblewrap, _docker
from vera.evolution.process import _process_stamp
from vera.memory.hindsight import HindsightMemory
from vera.plugins import PluginManager
from vera.storage import RunStore

ROLE = "review-kit-reviewer"
MCP_TOOL = "mcp_review-kit-fixture_echo"
PARENT_TASK = "ASSEMBLY PARENT PRIVATE TASK"
LONG_EVIDENCE = "parent MCP evidence: " + "x" * 2400


@pytest.fixture
def assembly(tmp_path, memory_service, web_service):
    """Install a real plugin and expose observable model/provider protocol endpoints."""
    pytest.importorskip("mcp")
    memory_url, memory_requests = memory_service
    search_url, search_requests = web_service
    HindsightMemory(memory_url, "test-project", api_key="fixture-key").retain("ASSEMBLY PROJECT MEMORY")
    key = tmp_path / "memory-key"
    key.write_text("fixture-key", encoding="utf-8")
    pid_file = tmp_path / "mcp-pids.txt"
    package = write_plugin(tmp_path / "market/plugins/review")
    shutil.copy(Path(__file__).with_name("mcp_fixture.py"), package / "mcp_fixture.py")
    (package / "server.py").write_text(
        "import os,runpy\nfrom pathlib import Path\n"
        "with Path(os.environ['ASSEMBLY_MCP_PID']).open('a') as output: output.write(str(os.getpid())+'\\n')\n"
        "runpy.run_path(str(Path(__file__).with_name('mcp_fixture.py')),run_name='__main__')\n",
        encoding="utf-8",
    )
    (package / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fixture": {
                        "command": sys.executable,
                        "args": ["${PLUGIN_ROOT}/server.py"],
                        "allow_tools": ["echo"],
                        "env_from": ["MCP_TEST_ALLOWED", "ASSEMBLY_MCP_PID"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    manifest = package / "plugin.json"
    manifest.write_text(
        json.dumps(
            json.loads(manifest.read_text())
            | {
                "extensions": {
                    "vera": {
                        "subagents": {
                            "reviewer": {
                                "description": "Verify the assembled runtime",
                                "instructions": "Use only delegated context.",
                                "tools": [MCP_TOOL, "web_search", "bash"],
                                "skills": ["review"],
                                "model": {
                                    "model_class": "tests.run.test_web_tools.LocalFixtureModel",
                                    "model_name": "assembly-child",
                                },
                            },
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    write_market(tmp_path / "market", [{"name": "review-kit", "source": "./plugins/review"}])
    manager = PluginManager(tmp_path / "user-config/plugins")
    manager.add_marketplace(str(tmp_path / "market"))
    manager.install_from_marketplace("review-kit", "team-market")
    manager.set_enabled("review-kit", True)
    write_skill(tmp_path / ".agents/skills", "private-parent-skill", "PARENT ONLY SKILL")
    profile = {
        "agent": {
            "agent_class": "hindsight",
            "system_template": "Use the available tools and finish.",
            "instance_template": "{{task}}",
            "context_budget_chars": 3200,
            "memory_shared_bank_id": "test-shared",
        },
        "model": {"model_class": "tests.run.test_web_tools.LocalFixtureModel", "model_name": "assembly-parent"},
        "plugins": {"directory": str(manager.directory), "names": ["review-kit"]},
        "web": {"search_provider": "searxng"},
        "sandbox": {"mode": "local", "workspace": str(tmp_path)},
    }
    parent_actions = iter(
        [
            ("skills_list", {}),
            ("skill_view", {"name": "review-kit-review"}),
            (MCP_TOOL, {"text": LONG_EVIDENCE}),
            ("web_search", {"query": "parent assembly evidence"}),
            ("subagent_run", {"role": ROLE, "task": "CHILD ONLY TASK"}),
            (
                "bash",
                {
                    "command": 'test "$(cat assembly-child.txt)" = assembled-child-ok && printf assembled-parent-ok > assembly-parent.txt'
                },
            ),
        ]
    )
    child_actions = iter(
        [
            ("skill_view", {"name": "review-kit-review"}),
            (MCP_TOOL, {"text": "child MCP evidence"}),
            ("web_search", {"query": "child assembly evidence"}),
            ("bash", {"command": "printf assembled-child-ok > assembly-child.txt"}),
            ("subagent_finish", {"summary": "assembled child complete"}),
        ]
    )
    observed = {"parent": [], "child": [], "finish": FINISH_CALL, "pid_stamp": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            actor = "child" if payload["model"] == "assembly-child" else "parent"
            observed[actor].append(payload)
            if observed["pid_stamp"] is None:
                observed["pid_stamp"] = _process_stamp(int(pid_file.read_text().strip()))
            action = next(child_actions) if actor == "child" else next(parent_actions, observed["finish"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_model_response([action], False)).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield {
                "profile": profile,
                "observed": observed,
                "memory": memory_requests,
                "search": search_requests,
                "environment": {
                    "VERA_TEST_MODEL_URL": f"http://127.0.0.1:{server.server_port}",
                    "HINDSIGHT_BASE_URL": memory_url,
                    "HINDSIGHT_BANK_ID": "test-project",
                    "HINDSIGHT_API_KEY_FILE": str(key),
                    "SEARXNG_URL": search_url,
                    "ASSEMBLY_MCP_PID": str(pid_file),
                    "MCP_TEST_ALLOWED": "allowed",
                    "MCP_TEST_PRIVATE": "must not reach MCP",
                    "OPENROUTER_API_KEY": "fixture-model-key",
                    "PYTHONUTF8": "1",
                },
            }
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize(
    "entry", ["cli", "weixin", "feishu", "cli-memory-outage", "cli-resume", "cli-docker", "cli-bubblewrap"]
)
def test_complete_runtime_assembly_across_entry_points(tmp_path, assembly, entry):
    """Follow actual provider calls, child artifacts, bounded context and durable receipts."""
    if entry in {"cli-docker", "cli-bubblewrap"}:
        backend = entry.removeprefix("cli-")
        if backend == "docker" and _docker(SandboxConfig()) is None:
            pytest.skip("Local Linux Docker engine or cached Python image unavailable")
        if backend == "bubblewrap" and _bubblewrap() is None:
            pytest.skip("Bubblewrap or working Linux namespaces unavailable")
        assembly["profile"]["sandbox"].update(
            mode=backend,
            host_mcp_servers=["review-kit-fixture"],
            allow_web_tools=True,
        )
    is_resume = entry == "cli-resume"
    if is_resume:
        assembly["profile"]["agent"]["step_limit"] = 6
    profile = tmp_path / "assembly.yaml"
    profile.write_text(yaml.safe_dump(assembly["profile"]), encoding="utf-8")
    database = tmp_path / "runs.sqlite3"
    observed = assembly["observed"]
    task = "Simulate service outage" if entry == "cli-memory-outage" else PARENT_TASK
    if entry.startswith("cli"):
        run_cli(
            tmp_path,
            "vera",
            "-c",
            "vera.yaml",
            "-c",
            str(profile),
            "-t",
            task,
            "--storage",
            str(database),
            "-o",
            str(tmp_path / "parent.json"),
            "-y",
            "--exit-immediately",
            **assembly["environment"],
        )
    else:
        observed["finish"] = ("channel_finish", {"summary": "assembled parent complete"})
        with ExitStack() as stack:
            messages = [weixin_message(1, text=PARENT_TASK)] if entry == "weixin" else []
            socket = stack.enter_context(feishu_socket([feishu_event(text=PARENT_TASK)])) if entry == "feishu" else None
            service = stack.enter_context(provider_service(messages, ws_url=socket["url"] if socket else ""))
            process, output, state = start_gateway(
                tmp_path, service, entry, agent_profile=assembly["profile"], model_environment=assembly["environment"]
            )
            try:
                wait_for(
                    lambda: ChannelStore(state).status()["tasks"].get("completed") == 1,
                    process,
                    tmp_path / "gateway.log",
                )
                wait_for(lambda: len(service["replies"]) >= 2, process, tmp_path / "gateway.log")
                assert "assembled parent complete" in json.dumps(service["replies"])
                with ChannelStore(state).connect() as db:
                    assert "calls=" in db.execute("SELECT progress FROM messages").fetchone()[0]
            finally:
                stop_gateway(process, output, state)
            assert process.returncode == 0
            database = state / "runs.sqlite3"

    assert (tmp_path / "assembly-child.txt").read_text() == "assembled-child-ok"
    assert (tmp_path / "assembly-parent.txt").read_text() == "assembled-parent-ok"
    store = RunStore(database)
    parent = store.get_run(next(row["id"] for row in store.list_runs() if row["parent_id"] is None))
    child = store.get_run(parent["children"][0]["id"])
    assert parent["status"] == ("stopped" if is_resume else "completed")
    assert child["status"] == "completed"
    assert parent["model_calls"] == (6 if is_resume else 7) and child["model_calls"] == 5
    assert parent["cost"] == pytest.approx(0.11 if is_resume else 0.12) and child["cost"] == pytest.approx(0.05)
    assert [row["tool"] for row in parent["tool_calls"]] == [
        "skills_list",
        "skill_view",
        MCP_TOOL,
        "web_search",
        "subagent_run",
        "bash",
    ] + ([] if is_resume else ["bash" if entry.startswith("cli") else "channel_finish"])
    assert all(row["status"] == "returned" for row in parent["tool_calls"] + child["tool_calls"])
    saved = json.loads(Path(parent["trajectory_path"]).read_text(encoding="utf-8"))
    assert saved["info"]["exit_status"] == ("LimitsExceeded" if is_resume else "Submitted")
    assert LONG_EVIDENCE in json.dumps(saved["messages"])
    assert "fixture-key" not in json.dumps(saved)
    assert ("ASSEMBLY PROJECT MEMORY" in observed["parent"][0]["messages"][1]["content"]) == (
        entry != "cli-memory-outage"
    )
    assert "Shared guidance" in observed["parent"][0]["messages"][1]["content"]
    assert "Older session history" in observed["parent"][-1]["messages"][1]["content"]
    assert len(observed["parent"][-1]["messages"]) < len(saved["messages"]) - 2
    child_messages = json.dumps(observed["child"])
    assert "CHILD ONLY TASK" in child_messages and "Plugin workflow body." in child_messages
    assert task not in child_messages and "ASSEMBLY PROJECT MEMORY" not in child_messages
    assert "PARENT ONLY SKILL" not in child_messages
    assert {tool["function"]["name"] for tool in observed["child"][0]["tools"]} == {
        MCP_TOOL,
        "web_search",
        "bash",
        "skills_list",
        "skill_view",
        "subagent_finish",
    }
    assert len(assembly["search"]) == 2
    assert len(assembly["memory"]) == 3 and assembly["memory"][-1][0].startswith("/v1/default/banks/test-shared/")
    assert '"private": false' in json.dumps(saved["messages"]).replace('\\"', '"')
    pids = (tmp_path / "mcp-pids.txt").read_text().splitlines()
    assert len(pids) == 1
    assert observed["pid_stamp"] and _process_stamp(int(pids[0])) != observed["pid_stamp"]

    if is_resume:
        run_cli(
            tmp_path,
            "vera",
            "-c",
            "vera.yaml",
            "-c",
            str(profile),
            "--storage",
            str(database),
            "--resume",
            parent["id"],
            "--reconcile",
            "Verified both assembly artifacts contain their expected results. Do not repeat previous actions.",
            "-o",
            str(tmp_path / "resumed.json"),
            "-y",
            "--exit-immediately",
            **assembly["environment"],
        )
        resumed = store.get_run(next(row["id"] for row in store.list_runs() if row["resumed_from"] == parent["id"]))
        assert resumed["status"] == "completed" and not resumed["children"]
        assert [row["tool"] for row in resumed["tool_calls"]] == ["bash"]
        assert len(assembly["memory"]) == 3 and len(observed["child"]) == 5
        assert len(observed["parent"]) == 7
        assert "ASSEMBLY PROJECT MEMORY" in observed["parent"][-1]["messages"][1]["content"]
        assert len((tmp_path / "mcp-pids.txt").read_text().splitlines()) == 2

    if entry == "cli":
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_cli(
                tmp_path,
                "vera",
                "-c",
                "vera.yaml",
                "-c",
                str(profile),
                "--storage",
                str(database),
                "--resume",
                parent["id"],
                "-o",
                str(tmp_path / "forbidden-resume.json"),
                **assembly["environment"],
            )
        assert "top-level run" in error.value.stderr
        assert len(observed["parent"]) == 7 and len(assembly["memory"]) == 3


def test_assembly_permissions_fail_before_model_tools_or_memory(tmp_path, assembly):
    """An unapproved host MCP/web exception blocks the fully configured runtime."""
    assembly["profile"]["sandbox"]["mode"] = "auto"
    config = tmp_path / "denied.yaml"
    config.write_text(yaml.safe_dump(assembly["profile"]), encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_cli(tmp_path, "vera", "-c", str(config), "-t", PARENT_TASK, **assembly["environment"])
    assert "sandbox.host_mcp_servers" in error.value.stderr and "sandbox.allow_web_tools" in error.value.stderr
    assert not assembly["observed"]["parent"] and not assembly["search"]
    assert len(assembly["memory"]) == 1
    assert not (tmp_path / "mcp-pids.txt").exists() and not (tmp_path / "assembly-child.txt").exists()
