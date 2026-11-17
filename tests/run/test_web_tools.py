"""Use real HTTP client paths against a local provider fixture and real Bash."""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.interactive import InteractiveAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.openrouter_model import OpenRouterModel
from minisweagent.models.openrouter_response_model import OpenRouterResponseModel
from minisweagent.tools import ToolSpec, make_tool_registry
from minisweagent.tools.web import firecrawl_provider, register_web_tools, searxng_provider, tavily_provider

PAGE = "https://example.org/docs"
WEB_CALLS = [("web_search", {"query": "pytest documentation", "limit": 2}), ("web_extract", {"url": PAGE})]
FINISH_CALL = ("bash", {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo done"})


def _model_response(calls, responses_api):
    items = []
    for index, (name, arguments) in enumerate(calls):
        function = {"name": name, "arguments": json.dumps(arguments)}
        if responses_api:
            items.append({"type": "function_call", "call_id": f"call_{index}", **function})
        else:
            items.append({"type": "function", "id": f"call_{index}", "function": function})
    if responses_api:
        return {"object": "response", "status": "completed", "output": items, "usage": {"cost": 0.01}}
    return {
        "choices": [{"message": {"role": "assistant", "content": "Read sources", "tool_calls": items}}],
        "usage": {"cost": 0.01},
    }


@pytest.fixture
def web_service():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            calls.append((url.path, parse_qs(url.query)))
            self._send(200, {"results": [{"url": PAGE, "title": "Documentation", "content": "SearXNG snippet"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            if self.path in {"/chat", "/responses", "/search-only"}:
                observations = body.get("input", body.get("messages", []))
                is_result = any(
                    row.get("role") == "tool" or row.get("type") == "function_call_output" for row in observations
                )
                actions = [FINISH_CALL] if is_result else WEB_CALLS[:1] if self.path == "/search-only" else WEB_CALLS
                self._send(200, _model_response(actions, self.path == "/responses"))
            elif self.headers.get("Authorization") != "Bearer fake-provider-key":
                self._send(401, {})
            elif self.path == "/v2/search":
                self._send(200, {"success": True, "data": {"web": [{"url": PAGE, "description": "Firecrawl snippet"}]}})
            elif self.path == "/v2/scrape":
                self._send(200, {"success": True, "data": {"markdown": "# Firecrawl body"}})
            elif self.path == "/search":
                self._send(200, {"results": [{"url": PAGE, "content": "Tavily snippet"}]})
            elif self.path == "/extract":
                self._send(200, {"results": [{"url": PAGE, "raw_content": "# Tavily body"}]})
            else:
                self._send(404, {})

        def _send(self, status, data):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", calls
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize(
    ("model_class", "endpoint"), [(OpenRouterModel, "/chat"), (OpenRouterResponseModel, "/responses")]
)
def test_model_declares_routes_and_receives_web_tools(web_service, model_class, endpoint):
    base_url, calls = web_service
    model = model_class(model_name="fixture")
    model._api_url = base_url + endpoint
    environment = LocalEnvironment()
    registry = make_tool_registry(environment)
    register_web_tools(
        registry, search=searxng_provider(base_url), extract=firecrawl_provider("fake-provider-key", base_url=base_url)
    )
    agent = DefaultAgent(
        model, environment, tool_registry=registry, system_template="Use tools.", instance_template="{{task}}"
    )
    assert agent.run("Read the project docs")["submission"] == "done\n"
    assert [path for path, _ in calls] == [endpoint, "/search", "/v2/scrape", endpoint]
    declarations = [item.get("function", item)["name"] for item in calls[0][1]["tools"]]
    assert declarations == ["bash", "web_search", "web_extract"]
    if endpoint == "/responses":
        assert all(item["strict"] is False for item in calls[0][1]["tools"])
    next_request = calls[-1][1]
    serialized = json.dumps(next_request)
    assert "SearXNG snippet" in serialized
    assert "Firecrawl body" in serialized
    assert "fake-provider-key" not in serialized


def test_search_and_extract_adapters_validate_before_request(web_service):
    base_url, calls = web_service
    registry = make_tool_registry(LocalEnvironment())
    tavily = tavily_provider("fake-provider-key", base_url=base_url)
    register_web_tools(registry, search=firecrawl_provider("fake-provider-key", base_url=base_url), extract=tavily)
    assert tavily.search("pytest", 1)[0]["snippet"] == "Tavily snippet"
    assert "Firecrawl snippet" in registry.execute({"tool": "web_search", "arguments": {"query": "pytest"}})["output"]
    assert "Tavily body" in registry.execute({"tool": "web_extract", "arguments": {"url": PAGE}})["output"]
    assert registry.execute({"tool": "web_search", "arguments": {"query": "pytest", "limit": -1}})["returncode"] == 1
    assert registry.execute({"tool": "web_extract", "arguments": {"url": "http://127.0.0.1/test"}})["returncode"] == 1
    assert registry.execute({"tool": "unknown", "arguments": {}})["returncode"] == 1
    assert [path for path, _ in calls] == ["/search", "/v2/search", "/extract"]


class DecliningAgent(InteractiveAgent):
    """Reject the first web request while allowing the existing completion marker."""

    def _prompt_and_handle_slash_commands(self, prompt, **kwargs):
        assert "Execute 1 action(s)?" in prompt
        return "Skip the external request"


def test_bash_whitelist_does_not_auto_approve_web_tool(web_service):
    base_url, calls = web_service
    model = OpenRouterModel(model_name="fixture")
    model._api_url = base_url + "/search-only"
    environment = LocalEnvironment()
    registry = make_tool_registry(environment)
    register_web_tools(registry, search=searxng_provider(base_url))
    agent = DecliningAgent(
        model,
        environment,
        tool_registry=registry,
        mode="confirm",
        whitelist_actions=[".*"],
        confirm_exit=False,
        system_template="Use tools.",
        instance_template="{{task}}",
    )
    assert agent.run("Search after confirmation")["exit_status"] == "Submitted"
    assert [path for path, _ in calls] == ["/search-only", "/search-only"]
    assert any(message.get("extra", {}).get("interrupt_type") == "UserRejection" for message in agent.messages)


class LocalFixtureModel(OpenRouterModel):
    """Use the production OpenRouter request/response code with a local endpoint."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._api_url = os.environ["MSWEA_TEST_MODEL_URL"]


def test_cli_enables_only_configured_web_capabilities(web_service, tmp_path):
    base_url, calls = web_service
    trajectory = tmp_path / "web.traj.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "minisweagent",
            "--agent-class",
            "interactive",
            "--model-class",
            "tests.run.test_web_tools.LocalFixtureModel",
            "-m",
            "fixture",
            "-c",
            "mini.yaml",
            "-c",
            "web.search_provider=searxng",
            "--exit-immediately",
            "-y",
            "-t",
            "Read public docs",
            "-o",
            str(trajectory),
        ],
        env=os.environ
        | {"MSWEA_TEST_MODEL_URL": base_url + "/search-only", "SEARXNG_URL": base_url, "MSWEA_CONFIGURED": "true"},
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    saved = json.loads(trajectory.read_text(encoding="utf-8"))
    assert saved["info"]["exit_status"] == "Submitted"
    assert [item["function"]["name"] for item in calls[0][1]["tools"]] == ["bash", "web_search"]
    assert [path for path, _ in calls] == ["/search-only", "/search", "/search-only"]


def test_registry_accepts_nonweb_capabilities():
    registry = make_tool_registry(LocalEnvironment())
    registry.register(
        ToolSpec(
            "echo_text",
            "Echo a string",
            {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}},
        ),
        lambda args: {"output": args["text"], "returncode": 0, "exception_info": ""},
    )
    assert registry.execute({"tool": "echo_text", "arguments": {"text": "hello"}})["output"] == "hello"
    assert registry.execute({"tool": "echo_text", "arguments": {"text": 1}})["returncode"] == 1
