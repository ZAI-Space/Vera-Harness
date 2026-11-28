"""A real local SSE peer proves deltas arrive before completion and survive stops."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from vera.desktop.service import DesktopService


@pytest.fixture(params=["chat", "responses"])
def streaming_desktop(tmp_path, request):
    arrived, release = threading.Event(), threading.Event()

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["stream"] is True
            if self.path.endswith("/responses"):
                self.send_responses_stream()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()

            def chunk(delta, finish=None, usage=None):
                value = {
                    "id": "chatcmpl-local",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "gpt-4o-mini",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
                if usage:
                    value["usage"] = usage
                self.wfile.write(("data: " + json.dumps(value) + "\n\n").encode())
                self.wfile.flush()

            try:
                chunk({"role": "assistant", "reasoning_content": "Visible reasoning from the provider. "})
                chunk({"content": "First "})
                chunk({"content": "streamed fragment. "})
                arrived.set()
                if not release.wait(30):
                    return
                chunk({"content": "Second streamed fragment."})
                chunk(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-real",
                                "type": "function",
                                "function": {
                                    "name": "bash",
                                    "arguments": '{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; ',
                                },
                            }
                        ]
                    }
                )
                chunk({"tool_calls": [{"index": 0, "function": {"arguments": 'echo stream-verified"}'}}]})
                chunk({}, "tool_calls", {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def send_responses_stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()

            def emit(kind, **fields):
                value = {"type": kind, **fields}
                self.wfile.write(("event: " + kind + "\ndata: " + json.dumps(value) + "\n\n").encode())
                self.wfile.flush()

            try:
                emit(
                    "response.reasoning_summary_text.delta",
                    output_index=0,
                    item_id="rs_local",
                    summary_index=0,
                    delta="Visible reasoning from the provider. ",
                )
                emit("response.output_text.delta", output_index=1, item_id="msg_local", content_index=0, delta="First ")
                emit(
                    "response.output_text.delta",
                    output_index=1,
                    item_id="msg_local",
                    content_index=0,
                    delta="streamed fragment. ",
                )
                arrived.set()
                if not release.wait(30):
                    return
                emit(
                    "response.output_text.delta",
                    output_index=1,
                    item_id="msg_local",
                    content_index=0,
                    delta="Second streamed fragment.",
                )
                call = {
                    "type": "function_call",
                    "id": "fc_local",
                    "call_id": "call-real",
                    "name": "bash",
                    "arguments": "",
                    "status": "in_progress",
                }
                emit("response.output_item.added", output_index=2, item=call)
                arguments = json.dumps({"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo stream-verified"})
                emit("response.function_call_arguments.delta", output_index=2, item_id="fc_local", delta=arguments)
                call.update(arguments=arguments, status="completed")
                emit(
                    "response.completed",
                    response={
                        "id": "resp_local",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": "gpt-4o-mini",
                        "output": [
                            {
                                "type": "reasoning",
                                "id": "rs_local",
                                "summary": [{"type": "summary_text", "text": "Visible reasoning from the provider. "}],
                            },
                            {
                                "type": "message",
                                "id": "msg_local",
                                "role": "assistant",
                                "status": "completed",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "First streamed fragment. Second streamed fragment.",
                                        "annotations": [],
                                    }
                                ],
                            },
                            call,
                        ],
                        "usage": {
                            "input_tokens": 40,
                            "output_tokens": 20,
                            "total_tokens": 60,
                            "input_tokens_details": {"cached_tokens": 0},
                            "output_tokens_details": {"reasoning_tokens": 0},
                        },
                    },
                )
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    peer = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    peer.daemon_threads = True
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    service = DesktopService(
        tmp_path / "state",
        {
            "model": {
                "model_class": "litellm_response" if request.param == "responses" else "litellm",
                "model_name": "openai/gpt-4o-mini",
                "model_kwargs": {
                    "api_base": f"http://127.0.0.1:{peer.server_port}/v1",
                    "api_key": "local-sse-only",
                    "timeout": 15,
                    "max_retries": 0,
                },
            },
            "agent": {"system_template": "Use Bash.", "instance_template": "{{task}}", "mode": "yolo", "cost_limit": 1},
        },
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    key = service.invoke("createSession", {"options": {"cwd": str(workspace)}})["sessionId"]
    service.invoke("setSessionSelections", {"sessionId": key, "permissionPolicy": "yolo"})
    yield service, key, arrived, release
    release.set()
    service.close()
    peer.shutdown()
    peer.server_close()
    thread.join(timeout=5)


def wait_for(predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if result := predicate():
            return result
        time.sleep(0.03)
    pytest.fail("Expected a real streaming worker event.")


def test_token_only_desktop_import_never_downloads_the_model_price_table():
    """A fresh SDK import must use bundled metadata without a price HTTP request."""
    script = """
import httpx
requests = []
def reject_download(*args, **kwargs):
    requests.append(True)
    raise AssertionError('Unexpected model price download')
httpx.get = reject_download
import vera.desktop.streaming
assert not requests, 'Desktop imported LiteLLM with remote price fetching enabled'
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=os.environ | {"LITELLM_LOCAL_MODEL_COST_MAP": "True", "VERA_SILENT_STARTUP": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_deltas_precede_completion_and_preserve_reasoning_and_tools(streaming_desktop, monkeypatch):
    service, key, arrived, release = streaming_desktop
    start_worker = subprocess.Popen

    def checked_worker(*args, **kwargs):
        # Even an inherited legacy setting must not re-enable the price download.
        assert kwargs["env"]["LITELLM_LOCAL_MODEL_COST_MAP"] == "True"
        return start_worker(*args, **kwargs)

    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "False")
    monkeypatch.setattr("vera.desktop.sessions.subprocess.Popen", checked_worker)
    service.invoke("prompt", {"sessionId": key, "text": "Stream the result."})
    assert arrived.wait(45)
    started = time.monotonic()
    live = wait_for(
        lambda: (
            service.sessions.get(key).get("liveStreaming", {}).get("text") == "First streamed fragment. "
            and "First streamed fragment. "
        )
    )
    assert live == "First streamed fragment. "
    assert key in service.sessions.running and not release.is_set()
    baseline = service.sessions.baseline(key)
    assert "Visible reasoning" in baseline["transcript"]["streaming"]["thinking"]
    assert any("First streamed fragment." in message["text"] for message in service.lan.snapshot(key)["messages"])
    release.set()
    assert time.monotonic() - started < 10, "Deltas must be observable while the provider is still waiting."
    wait_for(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    value = service.sessions.get(key)
    assert value["stats"]["inputTokens"] == 40 and value["stats"]["outputTokens"] == 20
    with sqlite3.connect(service.store.path) as db:
        timing = json.loads(db.execute("SELECT payload FROM desktop_performance").fetchone()[0])
    assert 0 <= timing["runtimeReadyMs"] <= timing["modelRequestMs"] <= timing["firstResponseMs"]
    assert timing["providerWaitMs"] == pytest.approx(timing["firstResponseMs"] - timing["modelRequestMs"])
    messages = value["messages"]
    assert any("First streamed fragment. Second streamed fragment." == row["text"] for row in messages)
    assert any("Visible reasoning" in row.get("thinking", "") for row in messages)
    assert any(tool["state"] == "done" for row in messages for tool in row.get("tools", []))
    assert any("stream-verified" in row["text"] for row in messages)
    trajectory = next((service.store.directory / "artifacts").rglob("trajectory.json"))
    assert "local-sse-only" not in trajectory.read_text(encoding="utf-8")
    events = service.events.read(0, 0)["events"]
    updates = [row["payload"]["event"] for row in events if row["method"] == "onEvent"]
    assert any(
        row["type"] == "message_update" and row["assistantMessageEvent"]["type"] == "thinking_delta" for row in updates
    )
    assert updates[-1]["type"] == "agent_settled"
    # The same complete event trace can be replayed by the frontend reducer.
    (service.store.directory / "event-trace.json").write_text(json.dumps(updates), encoding="utf-8")


def test_abort_keeps_received_text_and_does_not_execute_partial_tools(streaming_desktop):
    service, key, arrived, _ = streaming_desktop
    service.invoke("prompt", {"sessionId": key, "text": "Stop this stream."})
    assert arrived.wait(45)
    wait_for(lambda: service.sessions.get(key).get("liveStreaming", {}).get("text"))
    service.invoke("abort", {"sessionId": key})
    wait_for(lambda: not service.sessions.baseline(key)["transcript"]["agentActive"])
    value = service.sessions.get(key)
    assert any(row["text"] == "First streamed fragment. " for row in value["messages"])
    assert not value.get("liveStreaming")
    assert not value["runtimeMessages"]
