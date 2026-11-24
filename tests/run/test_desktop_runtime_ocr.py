"""Exercise desktop recovery paths with local files and bounded lifecycle fixtures."""

import json
import sqlite3
import subprocess
import threading
from contextlib import closing
from types import SimpleNamespace

import pytest
import requests

from vera.channels.store import ChannelStore
from vera.desktop.delegation import DelegatedConversations
from vera.desktop.events import LiveReply
from vera.desktop.model_settings import ModelOptions
from vera.desktop.providers import Providers
from vera.desktop.remote_connection import RemoteConnection
from vera.desktop.store import DesktopStore
from vera.desktop.taskboard import TaskboardService
from vera.desktop.taskboard_execution import TaskboardExecution


@pytest.mark.parametrize("payload", ['{"messages":', "[]", '{"messages": {}}', '{"messages": [null]}'])
def test_partial_delegated_trajectory_settles_and_keeps_live_output(tmp_path, payload):
    store = DesktopStore(tmp_path)
    emitted = []
    sessions = SimpleNamespace(
        store=store,
        get=lambda key: store.get("delegated-session", key),
        emit=lambda key, event: emitted.append(event),
        usage=None,
    )
    children = DelegatedConversations(sessions)
    parent = {"meta": {"cwd": str(tmp_path)}, "permissionMode": "default"}
    details = children.start("parent", parent, {"toolCallId": "call", "args": {"role": "reader", "task": "read"}})
    key = details["results"][0]["sessionFile"].partition(":")[2]
    live = LiveReply(None)
    live.apply({"update": {"type": "text_delta", "contentIndex": 0, "delta": "streamed result"}})
    children.live[key] = live
    trajectory = tmp_path / "artifacts" / "child.json"
    trajectory.parent.mkdir()
    trajectory.write_text(payload, encoding="utf-8")
    result = children.finish(
        parent,
        {
            "toolCallId": "call",
            "result": {"output": json.dumps({"trajectory": str(trajectory), "status": "Submitted"})},
        },
    )
    child = sessions.get(key)
    assert result["results"][0]["status"] == "done"
    assert not child["delegatedActive"] and key not in children.live
    assert child["messages"][-1]["text"] == "streamed result"
    assert emitted[-1] == {"type": "agent_settled", "aborted": False}


def test_removed_provider_reasoning_reports_validation_error(tmp_path):
    providers = Providers(DesktopStore(tmp_path))
    with pytest.raises(ValueError, match="provider no longer exists"):
        providers.reasoning_kwargs(
            {"provider": "deleted-fixture", "modelId": "gone"}, "high", ModelOptions().model_dump(by_alias=True)
        )


@pytest.mark.parametrize("status", [400, 500])
def test_discovery_http_failure_reports_status_without_response_secrets(tmp_path, monkeypatch, status):
    response = requests.Response()
    response.status_code = status
    response._content = b'{"error": "credential-must-not-be-echoed"}'
    monkeypatch.setattr("vera.desktop.providers.requests.get", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match=f"HTTP {status}") as failure:
        Providers(DesktopStore(tmp_path)).upstream({"baseUrl": "http://127.0.0.1:1/v1"})
    assert "credential-must-not-be-echoed" not in str(failure.value)


@pytest.mark.parametrize("payload", ["{", "[]", "{}", '{"directory": 1}', '{"directory": ""}'])
def test_corrupt_taskboard_descriptor_reports_not_installed(tmp_path, monkeypatch, payload):
    monkeypatch.delenv("VERA_TASKBOARD_HOME", raising=False)
    monkeypatch.setattr("vera.desktop.taskboard.global_config_dir", tmp_path)
    descriptor = tmp_path / "integrations/dashi-taskboard/current.json"
    descriptor.parent.mkdir(parents=True)
    descriptor.write_text(payload, encoding="utf-8")
    board = TaskboardService(DesktopStore(tmp_path / "desktop"))
    assert board.source() is None
    assert not board.status()["installed"]


@pytest.mark.parametrize("kill_succeeds", [True, False])
def test_taskboard_close_escalates_and_retains_ownership_until_exit(tmp_path, monkeypatch, kill_succeeds):
    class Process:
        pid = 123
        killed = False

        def poll(self):
            return 0 if self.killed and kill_succeeds else None

        def wait(self, timeout):
            if self.poll() is None:
                raise subprocess.TimeoutExpired("fixture", timeout)
            return 0

        def kill(self):
            self.killed = True

    monkeypatch.setattr("vera.desktop.taskboard._kill_tree", lambda pid: None)
    board = TaskboardService(DesktopStore(tmp_path))
    board.process = process = Process()
    board.url = "http://127.0.0.1:1/fixture/"
    if kill_succeeds:
        assert not board.close()["running"]
        assert board.process is None and board.url is None
    else:
        with pytest.raises(subprocess.TimeoutExpired):
            board.close()
        assert board.process is process and board.url
    assert process.killed


def test_pin_deadline_settles_login_and_allows_retry(tmp_path, monkeypatch):
    import vera.desktop.remote_connection as remote

    connection = RemoteConnection(SimpleNamespace(store=DesktopStore(tmp_path)), "weixin")
    clients = []

    class Client:
        closed = False

        def __init__(self):
            clients.append(self)

        def close(self):
            self.closed = True

    clock = iter([0, 481, 1000, 1481])
    monkeypatch.setattr(remote, "WeixinClient", Client)
    monkeypatch.setattr(
        remote,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda seconds: pytest.fail("Expired PIN must not wait")),
    )
    monkeypatch.setattr(remote, "login", lambda client, show_qr, read_pin, **kwargs: read_pin())
    for _ in range(2):
        connection.begin_login({"channel": "weixin"})
        connection.login_thread.join(timeout=2)
        assert not connection.login_thread.is_alive()
        assert connection.status()["loginState"] == "error"
        assert "超时" in connection.error
        assert not connection.credentials.has("weixin")
    assert all(client.closed for client in clients)


def test_failed_journal_migration_leaves_destination_retryable(tmp_path):
    connection = RemoteConnection(SimpleNamespace(store=DesktopStore(tmp_path)), "weixin")
    connection.directory.mkdir()
    legacy = connection.directory / "channels.sqlite3"
    with closing(sqlite3.connect(legacy)) as db, db:
        db.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
    destination = connection.directory / "weixin"
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        connection.migrate_journal(destination)
    assert not (destination / "channels.sqlite3").exists()
    assert not list(destination.glob("*.migrating"))
    legacy.unlink()
    source = ChannelStore(connection.directory)
    with source.connect() as db:
        db.execute("INSERT INTO cursors VALUES ('weixin', 'saved-cursor')")
    connection.migrate_journal(destination)
    assert ChannelStore(destination).cursor("weixin") == "saved-cursor"


@pytest.mark.parametrize("observer", ["snapshot", "watch"])
def test_taskboard_slow_sync_releases_observation_lock_and_comments_once(tmp_path, monkeypatch, observer):
    store = DesktopStore(tmp_path)
    execution = TaskboardExecution(SimpleNamespace(store=store, sessions=SimpleNamespace(running={})))
    run = {"sessionId": "run", "taskId": "task", "status": "running", "startedAt": 1, "error": None}
    store.save("taskboard-run", "run", run)
    store.save("session", "run", {"lastRunResult": {"exit_status": "Submitted", "submission": "done"}})
    execution.pending.add("run")
    arrived, release = threading.Event(), threading.Event()
    comments = []

    def request(method, path, **kwargs):
        if method == "GET" and path == "tasks/task":
            arrived.set()
            assert release.wait(3)
            return {"task": {"status": "in_progress", "version": 1}}
        if method == "POST":
            comments.append(kwargs["json"])
        return {"tasks": []}

    monkeypatch.setattr(execution, "request", request)
    errors = []

    def observe():
        try:
            getattr(execution, observer)()
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=observe, daemon=True)
    worker.start()
    assert arrived.wait(2)
    acquired = execution.lock.acquire(timeout=0.2)
    try:
        assert acquired, "Board synchronization must not own the dispatch/observation lock"
    finally:
        if acquired:
            execution.lock.release()
        execution.stopping.set()
        release.set()
        worker.join(timeout=3)
    assert not worker.is_alive() and not errors
    execution.sync(run | {"status": "completed"})
    assert len(comments) == 1
    assert store.get("taskboard-run", "run")["synced"]
