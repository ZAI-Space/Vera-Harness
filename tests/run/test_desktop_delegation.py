"""Verify cross-provider delegation and child inspection through real worker HTTP requests."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vera.desktop.service import DesktopService


def test_delegated_provider_credential_and_read_only_child_transcript(tmp_path):
    received = []
    child_started, release_child = threading.Event(), threading.Event()

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((body["model"], self.headers.get("Authorization")))
            child = body["model"] == "child"
            if child and not child_started.is_set():
                child_started.set()
                release_child.wait(20)
            done = any(row.get("role") == "tool" for row in body["messages"])
            if child:
                name, args = (
                    ("subagent_finish", {"summary": "CHILD_READ_VERIFIED"})
                    if done
                    else ("project_read", {"path": "README.md"})
                )
            else:
                name, args = "subagent_run", {"role": "reader", "task": "Read README.md and report evidence."}
            delta = {"role": "assistant"}
            if done and not child:
                delta["content"] = "PARENT_COMPLETED"
            else:
                delta["tool_calls"] = [
                    {
                        "index": 0,
                        "id": "call-" + str(len(received)),
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ]
            chunk = {
                "id": "response-" + str(len(received)),
                "object": "chat.completion.chunk",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {"index": 0, "delta": delta, "finish_reason": "stop" if done and not child else "tool_calls"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode())
            self.wfile.flush()

    peer = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("CHILD_FILE_EVIDENCE", encoding="utf-8")
    service = DesktopService(tmp_path / "state")
    try:
        for name in ("parent", "child"):
            service.providers.configure(
                {
                    "id": name,
                    "template": "custom",
                    "api": "openai-completions",
                    "apiKey": f"local-{name}-key",
                    "baseUrl": f"http://127.0.0.1:{peer.server_port}/v1",
                    "models": [{"id": name}],
                }
            )
        service.invoke(
            "saveSubagentRoles",
            {
                "roles": [
                    {
                        "name": "reader",
                        "description": "Read a file",
                        "instructions": "Read the file and return evidence.",
                        "enabled": True,
                        "tools": ["project_read"],
                        "skills": [],
                        "model": {"provider": "child", "modelId": "child"},
                    }
                ]
            },
        )
        meta = service.invoke(
            "createSession", {"options": {"cwd": str(workspace), "provider": "parent", "modelId": "parent"}}
        )
        key = meta["sessionId"]
        service.invoke("setSessionSelections", {"sessionId": key, "selections": {}, "permissionPolicy": "yolo"})
        service.invoke("prompt", {"sessionId": key, "text": "Delegate the file check."})
        assert child_started.wait(20)
        deadline = time.monotonic() + 10
        running_card = None
        while running_card is None and time.monotonic() < deadline:
            running_card = next(
                (row for row in service.sessions.baseline(key)["transcript"]["messages"] if row["kind"] == "subagent"),
                None,
            )
            time.sleep(0.01)
        assert running_card is not None
        assert running_card["runs"][0]["status"] == "running"
        sequences = [
            row["payload"]["sequence"]
            for row in service.events.read(0)["events"]
            if row["method"] == "onEvent" and row["payload"]["sessionId"] == key
        ]
        assert sequences == list(range(1, len(sequences) + 1))
        inspected = service.invoke("openSession", {"filePath": running_card["runs"][0]["sessionFile"]})
        child_id = inspected["sessionId"]
        before_close = service.sessions.get(child_id)
        assert before_close["delegatedActive"]
        assert service.invoke("closeSession", {"sessionId": child_id, "intent": "gc"}) == {"closed": True}
        assert service.sessions.get(child_id) == before_close
        assert service.store.get("session", child_id) is None
        assert child_id not in {row["sessionId"] for row in service.metas()}
        release_child.set()
        deadline = time.monotonic() + 45
        while service.sessions.baseline(key)["transcript"]["agentActive"] and time.monotonic() < deadline:
            time.sleep(0.05)
        parent = service.sessions.baseline(key)
        assert not parent["transcript"]["agentActive"]
        assert any(row.get("text") == "PARENT_COMPLETED" for row in parent["transcript"]["messages"])
        assert ("child", "Bearer local-child-key") in received
        card = next(row for row in parent["transcript"]["messages"] if row["kind"] == "subagent")
        run = card["runs"][0]
        assert run["status"] == "done"
        child = service.invoke("openSession", {"filePath": run["sessionFile"]})
        assert child["sessionId"] == child_id
        transcript = service.sessions.baseline(child["sessionId"])["transcript"]
        assert any(
            "CHILD_FILE_EVIDENCE" in tool["output"] for row in transcript["messages"] for tool in row.get("tools", [])
        )
        assert not transcript["agentActive"]
        assert child["sessionId"] not in {row["sessionId"] for row in service.metas()}
        child_sequences = [
            row["payload"]["sequence"]
            for row in service.events.read(0)["events"]
            if row["method"] == "onEvent" and row["payload"]["sessionId"] == child_id
        ]
        assert child_sequences == list(range(1, len(child_sequences) + 1))
        assert service.invoke("closeSession", {"sessionId": child_id}) == {"closed": True}
        assert service.store.get("session", child_id) is None
        with pytest.raises(ValueError, match="read-only"):
            service.invoke("prompt", {"sessionId": child["sessionId"], "text": "Do more"})
        for path in (service.store.directory / "artifacts").rglob("*.json"):
            assert "local-child-key" not in path.read_text(encoding="utf-8")
    finally:
        release_child.set()
        service.close()
        peer.shutdown()
        peer.server_close()
        thread.join(timeout=5)
