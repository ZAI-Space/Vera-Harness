"""Exercise general desktop turns through real HTTP streams, workers, tools and receipts."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from jinja2 import Template

from tests.run.test_web_tools import web_service  # noqa: F401
from vera.config import get_config_from_spec
from vera.desktop.prompts import refresh_legacy_history
from vera.desktop.service import DesktopService
from vera.runtime import open_agent_runtime
from vera.storage import RunStore


@pytest.fixture(params=["chat", "responses"])
def general_desktop(tmp_path, request):
    received = []

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(body)
            history = body.get("messages", body.get("input", []))
            prompt = json.dumps(history)
            observed = any(row.get("role") == "tool" or row.get("type") == "function_call_output" for row in history)
            web = "WEB_TASK" in prompt and not observed
            tool = ("TOOL_TASK" in prompt or web) and not observed
            tool_name = "web_search" if web else "bash"
            malformed = "BAD_TOOL" in prompt
            truncated = "TRUNCATED" in prompt and len(received) == 1
            empty = "EMPTY_REPLY" in prompt
            text = "我是 VERA，可以帮助你问答、写作和编程。" if not observed else "文件已写入，验证完成。"
            if empty:
                text = ""
            arguments = "not-json" if malformed else json.dumps({"command": "printf general-ok > general.txt"})
            if web:
                arguments = json.dumps({"query": "Python official documentation", "limit": 2})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
            self.end_headers()

            def send(value, kind=None):
                frame = (
                    ("event: " + kind + "\n" if kind else "")
                    + "data: "
                    + json.dumps(value, ensure_ascii=False)
                    + "\n\n"
                )
                self.wfile.write(frame.encode())
                self.wfile.flush()

            usage = {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 4},
            }
            if self.path.endswith("/responses"):
                output = (
                    [
                        {
                            "type": "function_call",
                            "id": "fc_local",
                            "call_id": "call_local",
                            "name": tool_name,
                            "arguments": arguments,
                            "status": "completed",
                        }
                    ]
                    if tool or malformed
                    else [
                        {
                            "type": "message",
                            "id": "msg_local",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": text, "annotations": []}],
                        }
                    ]
                )
                if not tool and not malformed and body.get("stream"):
                    send(
                        {
                            "type": "response.output_text.delta",
                            "output_index": 0,
                            "item_id": "msg_local",
                            "content_index": 0,
                            "delta": text,
                        },
                        "response.output_text.delta",
                    )
                status = "incomplete" if truncated else "completed"
                response = {
                    "id": "resp_local",
                    "object": "response",
                    "created_at": 1,
                    "status": status,
                    "model": "deepseek-flash",
                    "output": output,
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                        "input_tokens_details": {"cached_tokens": 4},
                    },
                }
                if truncated:
                    response["incomplete_details"] = {"reason": "max_output_tokens"}
                if not body.get("stream"):
                    self.wfile.write(json.dumps(response).encode())
                    return
                kind = "response." + status
                send({"type": kind, "response": response}, kind)
            else:
                delta = {"role": "assistant", "content": text}
                if tool or malformed:
                    delta["tool_calls"] = [
                        {
                            "index": 0,
                            "id": "call_local",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": arguments},
                        }
                    ]
                reason = "length" if truncated else "tool_calls" if tool or malformed else "stop"
                for part, finish, counters in ((delta, None, None), ({}, reason, usage)):
                    value = {
                        "id": "chatcmpl_local",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "deepseek-flash",
                        "choices": [{"index": 0, "delta": part, "finish_reason": finish}],
                    }
                    if counters:
                        value["usage"] = counters
                    send(value)
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

    peer = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    service = DesktopService(tmp_path / "state")
    service.providers.configure(
        {
            "id": "local",
            "name": "Unknown price model",
            "baseUrl": f"http://127.0.0.1:{peer.server_port}/v1",
            "api": "openai-responses" if request.param == "responses" else "openai-completions",
            "models": [{"id": "deepseek-flash"}],
        }
    )
    meta = service.invoke(
        "createSession", {"options": {"cwd": str(tmp_path), "provider": "local", "modelId": "deepseek-flash"}}
    )
    key = meta["sessionId"]
    service.invoke("setSessionSelections", {"sessionId": key, "permissionPolicy": "yolo", "selections": {}})

    def run(task):
        service.invoke("prompt", {"sessionId": key, "text": task})
        # Cold worker imports on shared Windows runners can exceed 30 seconds.
        deadline = time.monotonic() + 60
        while service.sessions.baseline(key)["transcript"]["agentActive"] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not service.sessions.baseline(key)["transcript"]["agentActive"]
        store = RunStore(service.store.directory / "runs.sqlite3")
        receipt = store.get_run(store.list_runs()[0]["id"])
        trajectory = json.loads(Path(receipt["trajectory_path"]).read_text())
        return receipt, trajectory

    try:
        yield service, key, received, run
    finally:
        service.close()
        peer.shutdown()
        peer.server_close()
        thread.join()


def test_plain_answer_needs_no_tools_or_price_and_has_one_completion(general_desktop, tmp_path):
    # The desktop worker must import the installed runtime, even in a Python project.
    project_package = tmp_path / "vera"
    project_package.mkdir()
    (project_package / "__init__.py").write_text("raise RuntimeError('Project package imported')\n", encoding="utf-8")
    service, key, received, run = general_desktop
    receipt, trajectory = run("你好，请你做一个自我介绍！")
    assert receipt["status"] == "completed" and receipt["exit_reason"] == "Submitted"
    assert receipt["tool_calls"] == [] and len(received) == 1
    history = received[0].get("messages", received[0].get("input"))
    assert "Recommended Workflow" not in json.dumps(history) and "at least one tool" not in json.dumps(history)
    messages = service.sessions.get(key)["messages"]
    assert len([row for row in messages if row["kind"] == "assistant"]) == 1
    assert "我是 VERA" in messages[-1]["text"]
    assert not (tmp_path / "general.txt").exists()
    assert not any("Run stopped: Submitted" in str(row) for row in service.events.read(0, timeout=0)["events"])
    assert trajectory["info"]["model_stats"]["token_usage"]["totalTokens"] == 15
    usage = service.invoke("getUsageStatistics", {})["totals"]
    assert usage["totalTokens"] == 15 and usage["requests"] == 1 and usage["cacheHitRate"] == 0.4
    run("继续自我介绍")
    assert len(received) == 2 and service.invoke("getUsageStatistics", {})["totals"]["requests"] == 2
    performance = service.invoke("getUsageStatistics", {})["performance"]
    assert performance["tasks"] == 2 and performance["firstResponseSamples"] == 2
    assert performance["completionRate"] == 1 and performance["retryMean"] == 0
    assert service.invoke("getUsageStatistics", {"cacheGroup": "first"})["totals"]["requests"] == 1
    assert service.invoke("getUsageStatistics", {"cacheGroup": "continued"})["totals"]["requests"] == 1


def test_tool_loop_continues_then_text_finishes_without_shell_marker(general_desktop, tmp_path):
    service, _, received, run = general_desktop
    receipt, trajectory = run("TOOL_TASK: write the requested file and report the result")
    assert receipt["status"] == "completed" and len(received) == 2
    assert (tmp_path / "general.txt").read_text() == "general-ok"
    assert len(receipt["tool_calls"]) == 1 and receipt["tool_calls"][0]["status"] == "returned"
    assert receipt["tool_calls"][0]["returncode"] == 0
    assert trajectory["info"]["model_stats"]["token_usage"]["totalTokens"] == 30
    assert service.invoke("getUsageStatistics", {})["totals"]["requests"] == 2
    assert service.invoke("getUsageStatistics", {})["performance"]["tools"][0]["calls"] == 1


def test_desktop_worker_uses_saved_web_service_and_tracks_search(general_desktop, web_service):
    """Saved desktop settings reach an isolated worker and the real HTTP search adapter."""
    service, key, received, run = general_desktop
    address, calls = web_service
    service.invoke(
        "saveWebSettings", {"provider": "searxng", "enabled": True, "readPages": False, "searxngUrl": address}
    )
    receipt, trajectory = run("WEB_TASK: search the web for Python documentation")
    assert receipt["exit_reason"] == "Submitted" and len(received) == 2
    assert any(row.get("function", row).get("name") == "web_search" for row in received[0]["tools"])
    assert calls[-1][0] == "/search"
    assert len(receipt["tool_calls"]) == 1 and receipt["tool_calls"][0]["returncode"] == 0
    assert service.invoke("getUsageStatistics", {})["performance"]["tools"][0]["name"] == "web_search"
    assert "SEARXNG_URL" not in json.dumps(trajectory)
    service.invoke(
        "saveWebSettings", {"provider": "searxng", "enabled": False, "readPages": False, "searxngUrl": address}
    )
    meta = service.invoke(
        "createSession",
        {
            "options": {
                "cwd": service.sessions.get(key)["meta"]["cwd"],
                "provider": "local",
                "modelId": "deepseek-flash",
            }
        },
    )
    assert not service.sessions.config(service.sessions.get(meta["sessionId"]))["web"]


def test_truncation_is_retried_and_every_consumed_response_is_counted(general_desktop):
    service, _, received, run = general_desktop
    receipt, trajectory = run("TRUNCATED: explain briefly")
    assert receipt["status"] == "completed" and len(received) == 2
    assert trajectory["info"]["model_stats"]["token_usage"]["reportedCalls"] == 2
    assert service.invoke("getUsageStatistics", {})["totals"]["totalTokens"] == 30
    performance = service.invoke("getUsageStatistics", {})["performance"]
    assert performance["retryMean"] == 1 and performance["firstResponseSamples"] == 0
    assert performance["errors"][0]["name"] == "FormatRetry"


@pytest.mark.parametrize("task", ["BAD_TOOL", "EMPTY_REPLY"])
def test_invalid_or_empty_responses_never_become_successful_finals(general_desktop, task, tmp_path):
    service, _, received, run = general_desktop
    receipt, _ = run(task)
    assert receipt["exit_reason"] == "RepeatedFormatError" and len(received) == 3
    assert receipt["tool_calls"] == [] and not (tmp_path / "general.txt").exists()
    assert service.invoke("getUsageStatistics", {})["totals"]["requests"] == 3


def test_legacy_wrapper_is_removed_without_rewriting_user_content():
    variables = {
        "system": "Windows",
        "release": "11",
        "version": "test",
        "machine": "AMD64",
        "task": "你好 {{ literal }}",
    }
    old = Template(get_config_from_spec("vera.yaml")["agent"]["instance_template"]).render(**variables)
    messages = [
        {"role": "user", "content": old},
        {"role": "user", "content": "Discuss Recommended Workflow in this document"},
        {"role": "tool", "content": old},
    ]
    refreshed = refresh_legacy_history(messages, variables)
    assert refreshed[0]["content"] == "你好 {{ literal }}"
    assert refreshed[1:] == messages[1:] and messages[0]["content"] == old


@pytest.mark.parametrize("mode", ["plan", "goal", "read-only"])
def test_explicit_modes_keep_their_finish_tools(general_desktop, mode):
    service, key, _, _ = general_desktop
    config = service.sessions.config(service.sessions.get(key))
    if mode == "read-only":
        config["permissions"] = {"mode": "read-only"}
    else:
        config["run_mode"] = mode
    with open_agent_runtime(config) as runtime:
        assert runtime.agent.model.config.allow_text_final is False
        names = {tool["function"]["name"] for tool in runtime.agent.tool_registry.definitions()}
        assert {"plan": "plan_finish", "goal": "goal_turn_finish", "read-only": "task_finish"}[mode] in names
