"""Exercise the desktop's real HTTP/process boundary, approvals and persistence."""

import json
import os
import subprocess
import sys
import threading
import time

import pytest
import requests

from vera.desktop.server import DesktopServer
from vera.desktop.service import DesktopService
from vera.storage import RunStore


@pytest.fixture
def desktop(tmp_path):
    config = {
        "model": {
            "model_class": "deterministic",
            "model_name": "fixture",
            "cost_per_call": 0,
            "outputs": [
                {
                    "role": "assistant",
                    "content": "Execute actual command",
                    "extra": {"actions": [{"command": "printf desktop-ok > actual.txt"}]},
                },
                {
                    "role": "assistant",
                    "content": "Finished",
                    "extra": {"actions": [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo verified"}]},
                },
            ],
        },
        "agent": {"system_template": "Use Bash.", "instance_template": "{{task}}", "mode": "yolo", "cost_limit": 1},
    }
    service = DesktopService(tmp_path / "state", config)
    server = DesktopServer(("127.0.0.1", 0), service, "test-desktop-token-" + "a" * 32)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer " + server.token}

    def invoke(method, **args):
        response = requests.post(url + "/invoke", headers=headers, json={"method": method, "args": args}, timeout=20)
        assert response.status_code == 200, response.text
        return response.json()["result"]

    yield service, invoke, url, headers
    service.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def wait_until(predicate):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail("Desktop worker did not reach the expected state.")


def test_server_expands_home_before_selecting_shared_context(tmp_path):
    """A quoted tilde path must use the same store and context as its absolute path."""
    home = tmp_path / "home"
    home.mkdir()
    connection = tmp_path / "connection.json"
    environment = os.environ | {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "VERA_GLOBAL_CONFIG_DIR": str(home / "vera"),
        "VERA_SILENT_STARTUP": "1",
    }
    with (tmp_path / "server.log").open("wb") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "vera.desktop.server",
                "--port",
                "0",
                "--directory",
                "~/vera/desktop",
                "--connection-file",
                str(connection),
            ],
            cwd=tmp_path,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            deadline = time.monotonic() + 60
            while not connection.exists():
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.05)
            address = json.loads(connection.read_text())
            response = requests.post(
                address["url"] + "/invoke",
                headers={"Authorization": "Bearer " + address["token"]},
                json={
                    "method": "saveUserContextEntry",
                    "args": {
                        "entry": {"kind": "rule", "title": "Shared context", "content": "Keep the shared profile."}
                    },
                },
                timeout=10,
            )
            assert response.status_code == 200, response.text
            assert (home / "vera/user-context/entries.json").is_file()
            assert not (home / "vera/desktop/user-context/entries.json").exists()
            assert not (tmp_path / "~").exists()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.parametrize(
    "method",
    [
        "searchCatalog",
        "installPackage",
        "removePackage",
        "listConfiguredPackages",
        "checkPackageUpdates",
        "getCacheWarming",
        "setCacheWarming",
    ],
)
def test_retired_settings_methods_are_rejected(desktop, method):
    """Retired panels must not leave callable package or cache-warming routes."""
    _, _, url, headers = desktop
    response = requests.post(url + "/invoke", headers=headers, json={"method": method, "args": {}}, timeout=10)
    assert response.status_code == 400
    assert "not supported" in response.json()["error"]


def test_real_desktop_run_files_history_and_restart(desktop, tmp_path):
    service, invoke, url, headers = desktop
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "context.txt").write_text("actual context", encoding="utf-8")
    assert requests.get(url + "/health", timeout=5).status_code == 401
    unknown = requests.post(
        url + "/invoke",
        headers=headers,
        json={"method": "__unknown_desktop_method__", "args": {}},
        timeout=5,
    )
    assert unknown.status_code == 400 and "not supported" in unknown.json()["error"]
    assert (
        requests.get(url + "/health", headers=headers | {"Origin": "https://example.com"}, timeout=5).status_code == 401
    )
    meta = invoke("createSession", options={"cwd": str(workspace)})
    key = meta["sessionId"]
    invoke("setSessionSelections", sessionId=key, permissionPolicy="yolo", selections={})
    assert "context.txt" in invoke("listProjectFiles", cwd=str(workspace))
    invoke("prompt", sessionId=key, text="Read @context.txt and execute.")
    wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    assert (workspace / "actual.txt").read_text() == "desktop-ok"
    baseline = invoke("getSessionBaseline", sessionId=key)
    assert baseline["sequence"] > 3
    assert any("verified" in message["text"] for message in baseline["transcript"]["messages"])
    assert service.sessions.get(key)["runtimeMessages"][1]["content"].find("actual context") >= 0
    events = requests.get(url + "/events?after=0", headers=headers, timeout=5).json()["events"]
    types = [row["payload"]["event"]["type"] for row in events if row["method"] == "onEvent"]
    assert "session_info_changed" in types and "tool_execution_start" in types and types[-1] == "agent_settled"
    assert list((service.store.directory / "artifacts").rglob("trajectory.json"))
    assert not list((service.store.directory / "artifacts").rglob("request.json"))
    restored = DesktopService(service.store.directory)
    assert (
        restored.invoke("getSessionBaseline", {"sessionId": key})["transcript"]["messages"]
        == baseline["transcript"]["messages"]
    )
    assert key in invoke("exportSession", sessionId=key, format="html") or "verified" in invoke(
        "exportSession", sessionId=key, format="html"
    )


def test_confirmation_scoping_and_cancel_prevent_unapproved_effects(desktop, tmp_path):
    service, invoke, url, headers = desktop
    workspace = tmp_path / "approval"
    workspace.mkdir()
    key = invoke("createSession", options={"cwd": str(workspace)})["sessionId"]
    invoke("prompt", sessionId=key, text="Wait for approval.")
    request = wait_until(lambda: next(iter(service.sessions.approvals.values()), None))
    assert not (workspace / "actual.txt").exists()
    wrong = requests.post(
        url + "/invoke",
        headers=headers,
        json={
            "method": "respondPermission",
            "args": {"requestId": request["id"], "sessionId": "other", "answer": "allow"},
        },
        timeout=5,
    )
    assert wrong.status_code == 400
    invoke("respondPermission", requestId=request["id"], answer="allow")
    wait_until(lambda: (workspace / "actual.txt").exists())
    wait_until(lambda: service.sessions.approvals)
    invoke("abort", sessionId=key)
    wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    assert invoke("getPendingInteractions")["permissions"] == []
    assert (workspace / "actual.txt").read_text() == "desktop-ok"


# Value: protects=unavailable saved sandboxes expose disabled choices and reasons;
# fails_when=the desktop reports a missing image as ready or omits its reason;
# why_new=the existing test only checked the saved profile name; seam=none;
# no_claim=availability of other configured container engines.
def test_provider_secrets_roles_and_unavailable_sandbox_are_real(desktop, tmp_path):
    service, invoke, _, _ = desktop
    secret = "fixture-private-value"
    invoke(
        "addCustomProvider",
        input={
            "id": "local-test",
            "name": "Local test",
            "api": "openai-completions",
            "baseUrl": "http://127.0.0.1:9876/v1",
            "apiKey": secret,
            "models": [{"id": "test-model", "name": "Test"}],
        },
    )
    assert secret not in json.dumps(invoke("listProviders"))
    assert service.providers.credentials()["local-test"] == secret
    role = {
        "id": "role",
        "name": "reviewer",
        "description": "Review",
        "instructions": "Read files.",
        "tools": ["bash"],
        "skills": [],
        "step_limit": 3,
        "cost_limit": 0.1,
        "wall_time_limit_seconds": 30,
        "enabled": True,
    }
    invoke("saveSubagentRoles", roles=[role])
    assert invoke("getSubagentRoles") == [role]
    profile = {
        "name": "unavailable",
        "mode": "docker",
        "workspace": str(tmp_path),
        "docker_image": "vera-missing-image-for-test:never",
    }
    invoke("saveSandboxProfiles", profiles=[profile])
    stored = invoke("getSandboxProfiles", cwd=str(tmp_path))
    assert stored["profiles"][0]["name"] == "unavailable"
    assert stored["status"]["configured"] is True and stored["status"]["enabled"] is False
    assert stored["status"]["choices"] == [
        {
            "name": "unavailable",
            "backend": "docker",
            "available": False,
            "code": "backend_unavailable",
            "reason": "A local Linux Docker engine must be running and the configured image must already be cached.",
        }
    ]
    assert stored["status"]["reason"] == "No available configured sandbox."
    commands = {row["name"]: row for row in invoke("listSlashCommandsForCwd", cwd=str(tmp_path))}
    assert commands["sandbox"]["supported"] is False
    assert commands["sandbox:unavailable"]["supported"] is False
    assert commands["sandbox:unavailable"]["description"] == stored["status"]["choices"][0]["reason"]
    assert commands["sandbox:unavailable"]["invocationName"] == "sandbox unavailable"


# Value: protects=one queued follow-up executes once and abort discards it even after worker exit;
# fails_when=queued work survives cancellation or restarts after the worker exits;
# why_new=existing desktop tests never prompt while a worker is running; seam=none;
# no_claim=external model quality or long-duration concurrency stability.
def test_queued_followup_executes_once_and_abort_discards_pending_work(desktop, tmp_path):
    service, invoke, url, headers = desktop
    service.sessions.base_config["model"]["outputs"][0]["extra"]["actions"][0]["command"] = (
        "printf 'run\\n' >> execution-count.txt"
    )
    workspace = tmp_path / "queued"
    workspace.mkdir()
    key = invoke("createSession", options={"cwd": str(workspace)})["sessionId"]

    def approval_for(session_id):
        return next((row for row in list(service.sessions.approvals.values()) if row["sessionId"] == session_id), None)

    invoke("prompt", sessionId=key, text="Run first task.")
    wait_until(lambda: approval_for(key))
    invoke("prompt", sessionId=key, text="Run one queued task.")
    assert invoke("getFollowUpMessages", sessionId=key) == ["Run one queued task."]
    rejected = requests.post(
        url + "/invoke",
        headers=headers,
        json={"method": "prompt", "args": {"sessionId": key, "text": "Reject a second queued task."}},
        timeout=5,
    )
    assert rejected.status_code == 400 and "already queued" in rejected.json()["error"]
    assert not (workspace / "execution-count.txt").exists()
    for _ in range(4):
        pending = wait_until(lambda: approval_for(key))
        invoke("respondPermission", sessionId=key, requestId=pending["id"], answer="allow")
    wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    assert (workspace / "execution-count.txt").read_text().splitlines() == ["run", "run"]
    assert invoke("getFollowUpMessages", sessionId=key) == []
    assert [row["text"] for row in invoke("getSessionMessages", sessionId=key) if row["role"] == "user"] == [
        "Run first task.",
        "Run one queued task.",
    ]

    cancelled_workspace = tmp_path / "cancelled-queue"
    cancelled_workspace.mkdir()
    cancelled_key = invoke("createSession", options={"cwd": str(cancelled_workspace)})["sessionId"]
    invoke("prompt", sessionId=cancelled_key, text="Cancel this active task.")
    wait_until(lambda: approval_for(cancelled_key))
    invoke("prompt", sessionId=cancelled_key, text="Do not run this queued task.")
    assert invoke("getFollowUpMessages", sessionId=cancelled_key) == ["Do not run this queued task."]
    invoke("abort", sessionId=cancelled_key)
    wait_until(lambda: not service.sessions.baseline(cancelled_key)["transcript"]["agentActive"])
    assert invoke("getPendingInteractions")["permissions"] == []
    assert invoke("getFollowUpMessages", sessionId=cancelled_key) == []
    assert not (cancelled_workspace / "execution-count.txt").exists()
    assert [row["text"] for row in invoke("getSessionMessages", sessionId=cancelled_key) if row["role"] == "user"] == [
        "Cancel this active task."
    ]
    restored = DesktopService(service.store.directory)
    assert restored.invoke("getFollowUpMessages", {"sessionId": cancelled_key}) == []

    service.sessions.base_config["model"]["outputs"] = [service.sessions.base_config["model"]["outputs"][-1]]
    race_workspace = tmp_path / "exited-worker-queue"
    race_workspace.mkdir()
    race_key = invoke("createSession", options={"cwd": str(race_workspace)})["sessionId"]
    invoke("setSessionSelections", sessionId=race_key, permissionPolicy="yolo", selections={})
    with service.sessions.lock:
        # A completion-only worker fits in stdout while its watcher waits for this lock.
        service.invoke("prompt", {"sessionId": race_key, "text": "Complete before the watcher settles."})
        service.invoke("prompt", {"sessionId": race_key, "text": "Do not replay the exited worker queue."})
        process = service.sessions.running[race_key]
        assert process.wait(timeout=20) == 0
        assert service.sessions.baseline(race_key)["transcript"]["agentActive"] is True
        service.invoke("abort", {"sessionId": race_key})
        pending_after_abort = service.invoke("getFollowUpMessages", {"sessionId": race_key})
        with pytest.raises(ValueError, match="stopping"):
            service.invoke("prompt", {"sessionId": race_key, "text": "Do not recreate a queue while stopping."})
    wait_until(lambda: not service.sessions.baseline(race_key)["transcript"]["agentActive"])
    assert pending_after_abort == []
    assert [row["text"] for row in invoke("getSessionMessages", sessionId=race_key) if row["role"] == "user"] == [
        "Complete before the watcher settles."
    ]


# Value: protects=fork and recall align visible history and retained pre-turn model context;
# fails_when=discarded future turns leak into a fork or recall mutates prior receipts;
# why_new=restart and export tests never exercised forkSession or recallMessage; seam=none;
# no_claim=undo of commands or filesystem side effects.
def test_fork_and_recall_keep_runtime_context_and_receipts_consistent(desktop, tmp_path):
    service, invoke, _, _ = desktop
    workspace = tmp_path / "history"
    workspace.mkdir()
    key = invoke("createSession", options={"cwd": str(workspace)})["sessionId"]
    invoke("setSessionSelections", sessionId=key, permissionPolicy="yolo", selections={})
    repeated_task = "Repeat this task."
    invoke("prompt", sessionId=key, text=repeated_task)
    wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    first = service.sessions.get(key)
    invoke("prompt", sessionId=key, text=repeated_task)
    wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    complete = service.sessions.get(key)
    user_turns = [row for row in complete["messages"] if row["kind"] == "user"]
    assert [row["text"] for row in user_turns] == [repeated_task, repeated_task]
    second = user_turns[1]
    assert second["runtimeIndex"] == len(first["runtimeMessages"]) > 0
    assert complete["runtimeMessages"][: second["runtimeIndex"]] == first["runtimeMessages"]
    receipts = {path: path.read_bytes() for path in (service.store.directory / "artifacts").rglob("trajectory.json")}
    assert len(receipts) == len(RunStore(service.store.directory / "runs.sqlite3").list_runs()) == 2
    reference = {"entryId": second["entryId"], "text": repeated_task}
    fork = invoke("forkSession", sessionId=key, ref=reference)
    child_key = fork["sessionId"]
    child = service.sessions.get(child_key)
    assert child["messages"] == first["messages"]
    assert child["runtimeMessages"] == first["runtimeMessages"]
    assert fork["messageCount"] == len(child["messages"])
    assert service.sessions.get(key) == complete

    invoke("setSessionSelections", sessionId=child_key, permissionPolicy="yolo", selections={})
    invoke("prompt", sessionId=child_key, text="Continue only inside the fork.")
    wait_until(lambda: not service.sessions.baseline(child_key)["transcript"]["agentActive"])
    continued_child = service.sessions.get(child_key)
    assert "Continue only inside the fork." in json.dumps(continued_child["runtimeMessages"])
    assert continued_child["runtimeMessages"][: len(first["runtimeMessages"])] == first["runtimeMessages"]
    assert (
        sum(
            row.get("role") == "user" and row.get("content") == repeated_task
            for row in continued_child["runtimeMessages"]
        )
        == 1
    )
    assert service.sessions.get(key) == complete
    assert invoke("recallMessage", sessionId=key, ref=reference) == {
        "text": repeated_task,
        "images": [],
        "document": None,
    }
    recalled = service.sessions.get(key)
    assert recalled["messages"] == first["messages"]
    assert recalled["runtimeMessages"] == first["runtimeMessages"]
    assert recalled["meta"]["messageCount"] == len(recalled["messages"])
    assert service.sessions.get(child_key) == continued_child
    for invalid_id in ("missing", "", None):
        with pytest.raises(ValueError, match="Message no longer exists"):
            service.invoke("forkSession", {"sessionId": key, "ref": {"entryId": invalid_id, "text": repeated_task}})
    legacy_fork = invoke("forkSession", sessionId=child_key, ref={"text": "Continue only inside the fork."})
    assert service.sessions.get(legacy_fork["sessionId"])["runtimeMessages"] == first["runtimeMessages"]
    assert service.sessions.get(legacy_fork["sessionId"])["messages"] == first["messages"]
    assert service.sessions.get(child_key) == continued_child
    assert (workspace / "actual.txt").read_text() == "desktop-ok"
    assert all(path.read_bytes() == content for path, content in receipts.items())
    assert len(RunStore(service.store.directory / "runs.sqlite3").list_runs()) == 3


def test_settings_contract_human_mode_and_slash_status(desktop, tmp_path):
    service, invoke, _, _ = desktop
    workspace = tmp_path / "manual"
    workspace.mkdir()
    service.store.save(
        "settings", "mcp", {"must-not-start": {"enabled": True, "config": {"command": "missing-qa-service"}}}
    )
    key = invoke("createSession", options={"cwd": str(workspace), "provider": "unconfigured", "modelId": "chat"})[
        "sessionId"
    ]
    assert invoke("setModelHidden", provider="openai", modelId="gpt-4o-mini", hidden=True)["hiddenModels"] == {
        "openai": ["gpt-4o-mini"]
    }
    assert (
        invoke("setSubagentModel", agent="reviewer", modelRef="openai/gpt-4o-mini")["subagentModels"]["reviewer"]
        == "openai/gpt-4o-mini"
    )
    assert invoke("setSubagentThinking", agent="reviewer", level="low")["subagentThinking"]["reviewer"] == "low"
    invoke("setSessionSelections", sessionId=key, permissionPolicy="human", selections={})
    invoke("prompt", sessionId=key, text="printf manual-ok > manual.txt")
    wait_until(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    assert (workspace / "manual.txt").read_text() == "manual-ok"
    invoke("prompt", sessionId=key, text="/help")
    assert "/goal" in invoke("getSessionMessages", sessionId=key)[-1]["text"]
    assert invoke("getSessionMessages", sessionId=key)[-1]["role"] == "assistant"
    assert not invoke("getSessionBaseline", sessionId=key)["transcript"]["agentActive"]


def test_goal_state_survives_the_real_worker_environment(desktop, tmp_path):
    """The worker's private global directory must not change an already-created goal's location."""
    import os
    import subprocess
    import sys

    from vera.terminal.session import TerminalSession

    service, invoke, _, _ = desktop
    key = invoke("createSession", options={"cwd": str(tmp_path)})["sessionId"]
    config = service.sessions.config(service.sessions.get(key))
    session = TerminalSession(config, tmp_path)
    session.process("/goal Verify the desktop goal boundary")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json,sys; from pathlib import Path; from vera.terminal.session import TerminalSession; "
                "config=json.load(sys.stdin); "
                "print(json.dumps(TerminalSession(config, Path(config['sandbox']['workspace'])).goals.status()))"
            ),
        ],
        input=json.dumps(config),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env=os.environ | {"VERA_GLOBAL_CONFIG_DIR": str(service.store.directory), "VERA_SILENT_STARTUP": "1"},
    )
    state = json.loads(result.stdout)
    assert state["status"] == "active"
    assert state["objective"] == "Verify the desktop goal boundary"


def test_scheduler_adapter_runs_a_real_persisted_job(desktop, tmp_path):
    from vera.scheduler.engine import service_status, stop_service

    service, invoke, _, _ = desktop
    workspace = tmp_path / "scheduled-work"
    workspace.mkdir()
    directory = service.store.directory / "scheduler"
    try:
        state = invoke(
            "saveScheduledTask",
            draft={
                "title": "Actual schedule",
                "prompt": "Execute verification.",
                "workspacePath": str(workspace),
                "cadence": "manual",
                "schedule": None,
                "permissionMode": "yolo",
                "sessionMode": "perRun",
                "modelRef": "",
                "thinkingLevel": "inherit",
            },
        )
        task = state["tasks"][0]
        assert task["enabled"] is False
        invoke("scheduledAction", id=task["id"], action="run")
        wait_until(lambda: any(row["status"] in {"completed", "error"} for row in invoke("getScheduledTasks")["runs"]))
        result = invoke("getScheduledTasks")["runs"][0]
        assert result["status"] == "completed", result
        assert (workspace / "actual.txt").read_text() == "desktop-ok"
        invoke("scheduledAction", id=task["id"], action="remove")
        assert not invoke("getScheduledTasks")["tasks"]
    finally:
        stop_service(directory)
        wait_until(lambda: not service_status(directory)["running"])


def test_desktop_read_tools_share_file_scope_without_shell_permission(tmp_path):
    from vera.desktop.project_tools import register_project_tools
    from vera.tools import ToolRegistry

    (tmp_path / "allowed.txt").write_text("specific searchable text", encoding="utf-8")
    (tmp_path / ".env").write_text("PRIVATE=hidden", encoding="utf-8")
    registry = ToolRegistry()
    register_project_tools(registry, tmp_path)
    assert {row["function"]["name"] for row in registry.definitions()} == {
        "project_read",
        "project_files",
        "project_search",
    }
    assert (
        "specific searchable text"
        in registry.execute({"tool": "project_read", "arguments": {"path": "allowed.txt"}})["output"]
    )
    assert (
        "allowed.txt:1:" in registry.execute({"tool": "project_search", "arguments": {"query": "searchable"}})["output"]
    )
    assert registry.execute({"tool": "project_read", "arguments": {"path": ".env"}})["returncode"] == 1
    assert registry.execute({"tool": "bash", "arguments": {"command": "printf unexpected"}})["returncode"] == 1
