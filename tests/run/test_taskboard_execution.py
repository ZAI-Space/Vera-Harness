"""Exercise the installed board, HTTP model peer and real desktop workers without mocks."""

import json
import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vera.desktop.service import DesktopService

pytestmark = pytest.mark.skipif(
    not os.getenv("VERA_TASKBOARD_HOME") or not shutil.which("node"), reason="Requires installed upstream Taskboard"
)


def until(predicate):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(0.05)
    pytest.fail("Taskboard execution did not settle")


@pytest.fixture
def linked_board(tmp_path):
    arrived, release = threading.Event(), threading.Event()
    release.set()

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            arrived.set()
            release.wait(40)
            finished = any(row["role"] == "tool" for row in body["messages"])
            delta = (
                {"content": "Verified taskboard execution."}
                if finished
                else {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "board-call",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": "printf board-linked > board-proof.txt"}),
                            },
                        }
                    ],
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            frames = [
                {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if finished else "tool_calls"}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                },
            ]
            try:
                for frame in frames:
                    frame.update(id="board-local", object="chat.completion.chunk", created=1, model="board-model")
                    self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    peer = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    peer.daemon_threads = True
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    service = DesktopService(tmp_path / "state")
    service.providers.configure(
        {
            "id": "board-local",
            "name": "Board local peer",
            "api": "openai-completions",
            "baseUrl": f"http://127.0.0.1:{peer.server_port}/v1",
            "models": [{"id": "board-model"}],
        }
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service.taskboard.start()
    task = service.taskboard_execution.request("POST", "tasks", json={"title": "Real board execution"})["task"]
    args = {
        "taskId": task["id"],
        "version": task["version"],
        "cwd": str(workspace),
        "provider": "board-local",
        "modelId": "board-model",
        "thinkingLevel": "default",
    }
    yield service, task, args, workspace, arrived, release
    release.set()
    service.close()
    peer.shutdown()
    peer.server_close()
    thread.join(timeout=5)


def test_board_dispatch_approval_live_chat_receipt_and_restart(linked_board):
    service, task, args, workspace, _, _ = linked_board
    run = service.invoke("runTaskboardTask", args)
    approval = until(lambda: next(iter(service.sessions.approvals.values()), None))
    assert service.sessions.baseline(run["sessionId"])["transcript"]["agentActive"]
    assert not (workspace / "board-proof.txt").exists()
    latest = service.taskboard_execution.request("GET", "tasks/" + task["id"])["task"]
    with pytest.raises(ValueError, match="已在执行"):
        service.invoke("runTaskboardTask", args | {"version": latest["version"]})
    with pytest.raises(ValueError, match="停止任务"):
        service.invoke("stopTaskboard")
    service.sessions.respond({"sessionId": run["sessionId"], "requestId": approval["id"], "answer": "allow"})
    saved = until(
        lambda: row if (row := service.store.get("taskboard-run", run["sessionId"]))["status"] != "running" else None
    )
    until(lambda: service.store.get("taskboard-run", run["sessionId"]).get("synced"))
    assert saved["status"] == "completed", saved
    assert (workspace / "board-proof.txt").read_text() == "board-linked"
    assert service.taskboard_execution.request("GET", "tasks/" + task["id"])["task"]["status"] == "in_review"
    service.invoke("syncTaskboardRun", {"sessionId": run["sessionId"]})
    assert len(service.taskboard_execution.request("GET", "tasks/" + task["id"] + "/comments")["comments"]) == 1
    service.taskboard.close()
    service.taskboard.start()
    assert service.invoke("getTaskboardExecution")["runs"][0]["status"] == "completed"
    assert service.sessions.get(run["sessionId"])["messages"][-1]["text"] == "Verified taskboard execution."


def test_board_cancel_is_blocked_and_invalid_requests_leave_no_chats(linked_board):
    service, task, args, workspace, arrived, release = linked_board
    for invalid, message in [
        (args | {"version": 999}, "任务已更新"),
        (args | {"modelId": "absent"}, "模型已被移除"),
        (args | {"permissionPolicy": "human"}, "仅支持"),
    ]:
        with pytest.raises(ValueError, match=message):
            service.invoke("runTaskboardTask", invalid)
    assert not service.metas() and not service.store.list("taskboard-run")
    release.clear()
    run = service.invoke("runTaskboardTask", args | {"permissionPolicy": "yolo"})
    assert arrived.wait(30)
    service.sessions.abort(run["sessionId"])
    saved = until(
        lambda: row if (row := service.store.get("taskboard-run", run["sessionId"]))["status"] != "running" else None
    )
    assert saved["status"] == "error" and saved["error"] == "Cancelled"
    until(lambda: service.store.get("taskboard-run", run["sessionId"]).get("synced"))
    assert service.taskboard_execution.request("GET", "tasks/" + task["id"])["task"]["status"] == "blocked"
    assert not (workspace / "board-proof.txt").exists()
