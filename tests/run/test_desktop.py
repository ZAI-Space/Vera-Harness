"""Exercise the desktop's real HTTP/process boundary, approvals and persistence."""

import json
import threading
import time

import pytest
import requests

from vera.desktop.server import DesktopServer
from vera.desktop.service import DesktopService


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


def test_real_desktop_run_files_history_and_restart(desktop, tmp_path):
    service, invoke, url, headers = desktop
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "context.txt").write_text("actual context", encoding="utf-8")
    assert requests.get(url + "/health", timeout=5).status_code == 401
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
    assert "tool_execution_start" in types and types[-1] == "agent_settled"
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


def test_settings_contract_human_mode_and_slash_status(desktop, tmp_path):
    service, invoke, _, _ = desktop
    workspace = tmp_path / "manual"
    workspace.mkdir()
    key = invoke("createSession", options={"cwd": str(workspace)})["sessionId"]
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
