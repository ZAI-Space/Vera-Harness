"""Exercise the official client against real stdio and Streamable HTTP servers."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from threading import Thread
from time import monotonic, sleep

import pytest
import yaml

from vera.tools import ToolError, ToolRegistry, ToolSpec
from vera.tools.mcp import open_mcp_tools, parse_mcp_servers

pytest.importorskip("mcp")

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse

from tests.run.mcp_fixture import make_server
from tests.run.test_web_tools import FINISH_CALL, _model_response

FIXTURE_PATH = Path(__file__).with_name("mcp_fixture.py")
ECHO_CALL = {"tool": "mcp_fixture_echo", "arguments": {"text": "hello from MCP"}}


def test_stdio_discovers_tools_and_dispatches_errors():
    registry = ToolRegistry()
    configs = parse_mcp_servers(
        {
            "fixture": {
                "command": sys.executable,
                "args": [str(FIXTURE_PATH)],
                "allow_tools": ["echo", "fail"],
            }
        }
    )
    with open_mcp_tools(registry, configs):
        assert {item["function"]["name"] for item in registry.definitions()} == {"mcp_fixture_echo", "mcp_fixture_fail"}
        assert json.loads(registry.execute(ECHO_CALL)["output"])["text"] == "hello from MCP"
        assert registry.execute(ECHO_CALL | {"arguments": {"text": 5}})["returncode"] == 1
        failed = registry.execute({"tool": "mcp_fixture_fail", "arguments": {}})
        assert failed["returncode"] == 1
        assert "fixture refused" in failed["output"]
    assert registry.execute(ECHO_CALL)["returncode"] == 1


def test_stdio_allowlist_rejects_unknown_names():
    configs = parse_mcp_servers(
        {"fixture": {"command": sys.executable, "args": [str(FIXTURE_PATH)], "allow_tools": ["misspelled"]}}
    )
    with pytest.raises(ToolError, match="MCP tools not found: misspelled"), open_mcp_tools(ToolRegistry(), configs):
        pytest.fail("Startup must fail before entering the run.")


@pytest.fixture
def http_server():
    app = make_server().streamable_http_app()
    requests = []
    model_requests = []

    async def fixture_app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/model":
            payload = await Request(scope, receive).json()
            model_requests.append(payload)
            has_result = any(message["role"] == "tool" for message in payload["messages"])
            actions = [FINISH_CALL] if has_result else [(ECHO_CALL["tool"], ECHO_CALL["arguments"])]
            await JSONResponse(_model_response(actions, False))(scope, receive, send)
            return
        if scope["type"] == "http":
            requests.append((scope["method"], dict(scope["headers"]).get(b"authorization")))
        await app(scope, receive, send)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        http = uvicorn.Server(uvicorn.Config(fixture_app, log_level="warning", interface="asgi3"))
        thread = Thread(target=http.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = monotonic() + 10
            while not http.started and thread.is_alive() and monotonic() < deadline:
                sleep(0.02)
            assert http.started
            yield f"http://127.0.0.1:{port}", requests, model_requests
        finally:
            http.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_multiple_sessions_forward_token_and_close(http_server):
    url, requests, _ = http_server
    variable = "MCP_TEST_BEARER"
    previous_token = os.environ.get(variable)
    token = os.environ[variable] = "fixture-token"
    try:
        registry = ToolRegistry()
        configs = parse_mcp_servers(
            {
                "fixture": {"url": f"{url}/mcp", "bearer_token_env": variable, "allow_tools": ["echo"]},
                "local": {"command": sys.executable, "args": [str(FIXTURE_PATH)], "allow_tools": ["echo"]},
            }
        )
        with open_mcp_tools(registry, configs):
            assert json.loads(registry.execute(ECHO_CALL)["output"])["text"] == "hello from MCP"
            assert (
                json.loads(registry.execute(ECHO_CALL | {"tool": "mcp_local_echo"})["output"])["text"]
                == "hello from MCP"
            )
            assert [item["name"] for item in registry.definitions(responses=True)] == [
                "mcp_fixture_echo",
                "mcp_local_echo",
            ]
        assert requests[-1][0] == "DELETE"
        assert all(value == f"Bearer {token}".encode() for _, value in requests)
    finally:
        if previous_token is None:
            del os.environ[variable]
        else:
            os.environ[variable] = previous_token


def test_registry_resolves_in_document_schemas_without_fetching_remote_refs(http_server):
    url, requests, _ = http_server
    registry = ToolRegistry()
    fields = {"type": "object", "$defs": {"text": {"type": "string"}}}
    for name, reference in [("local_ref", "#/$defs/text"), ("http_ref", f"{url}/schema")]:
        schema = fields | {"properties": {"text": {"$ref": reference}}}
        registry.register(ToolSpec(name, name, schema), lambda args: {"returncode": 0, "output": args["text"]})
    action = {"tool": "local_ref", "arguments": {"text": "hello"}}
    assert registry.execute(action)["output"] == "hello"
    assert "Unresolved schema reference" in registry.execute(action | {"tool": "http_ref"})["exception_info"]
    assert not requests


def test_cli_routes_mcp_and_bash_with_selective_environment(tmp_path, http_server):
    url, _, model_requests = http_server
    config = tmp_path / "mcp.yaml"
    trajectory = tmp_path / "mcp.traj.json"
    config.write_text(
        yaml.safe_dump(
            {
                "mcp_servers": {
                    "fixture": {
                        "command": sys.executable,
                        "args": [str(FIXTURE_PATH)],
                        "allow_tools": ["echo"],
                        "env_from": ["MCP_TEST_ALLOWED"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "vera",
            "--model-class",
            "tests.run.test_web_tools.LocalFixtureModel",
            "--model",
            "fixture",
            "-c",
            "vera.yaml",
            "-c",
            str(config),
            "--exit-immediately",
            "-y",
            "-t",
            "Run the echo tool",
            "-o",
            str(trajectory),
        ],
        env=os.environ
        | {
            "VERA_CONFIGURED": "true",
            "MCP_TEST_ALLOWED": "yes",
            "MCP_TEST_PRIVATE": "yes",
            "VERA_TEST_MODEL_URL": f"{url}/model",
        },
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    saved = json.loads(trajectory.read_text(encoding="utf-8"))
    assert saved["info"]["exit_status"] == "Submitted"
    assert [tool["function"]["name"] for tool in model_requests[0]["tools"]] == ["bash", "mcp_fixture_echo"]
    assert len(model_requests) == 2
    observation = next(message for message in model_requests[1]["messages"] if message["role"] == "tool")
    result = json.loads(observation["content"])
    assert result["returncode"] == 0
    assert json.loads(result["output"]) == {"text": "hello from MCP", "allowed": True, "private": False}
