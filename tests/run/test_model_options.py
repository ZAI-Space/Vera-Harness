"""Validate persisted model settings at the real local HTTP request boundary."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from vera.desktop.model_settings import ModelOptions, apply_reasoning, endpoint_base
from vera.desktop.service import DesktopService
from vera.models import get_model


def test_worker_restores_a_different_subagent_provider_without_persisting_keys(tmp_path):
    """Each role's reference resolves its own encrypted credential after the safe handoff."""
    from vera.desktop.providers import restore_model_config
    from vera.utils.serialize import strip_sensitive

    service = DesktopService(tmp_path)
    try:
        for name in ("parent", "child"):
            service.providers.configure(
                {
                    "id": name,
                    "template": "custom",
                    "api": "openai-completions",
                    "baseUrl": "https://example.invalid/v1",
                    "apiKey": f"local-{name}-credential",
                    "models": [{"id": name}],
                }
            )
        parent = {"provider": "parent", "modelId": "parent"}
        child = {"provider": "child", "modelId": "child"}
        remote = {"url": "https://example.invalid/mcp", "headers_from": {"X-Api-Key": "MCP_API_KEY"}}
        config = strip_sensitive(
            {
                "model": service.providers.model_config(parent),
                "subagents": {"roles": {"reviewer": {"model": service.providers.model_config(child)}}},
                "desktop_subagent_refs": {"reviewer": child},
                "mcp_servers": {"remote": remote},
            }
        )
        assert "local-child-credential" not in json.dumps(config)
        assert config["mcp_servers"]["remote"] == remote
        restore_model_config(config, str(tmp_path), parent)
        assert config["model"]["model_kwargs"]["api_key"] == "local-parent-credential"
        assert config["subagents"]["roles"]["reviewer"]["model"]["model_kwargs"]["api_key"] == "local-child-credential"
        assert config["mcp_servers"]["remote"] == remote
    finally:
        service.close()


def test_api_configuration_survives_restart_without_account_login_capabilities(tmp_path):
    """Removing account auth must retain API credentials, model references and preferences."""
    service = DesktopService(tmp_path)
    try:
        service.providers.configure(
            {
                "id": "api-only",
                "baseUrl": "https://fixture.invalid/v1",
                "api": "openai-completions",
                "apiKey": "local-fixture-only",
                "models": [{"id": "test-model"}],
            }
        )
    finally:
        service.close()
    restored = DesktopService(tmp_path)
    try:
        providers = restored.invoke("listProviders")
        configured = next(item for item in providers if item["id"] == "api-only")
        assert configured["configured"] and configured["authType"] == "api_key"
        assert all("oauth" not in item for item in providers)
        assert "local-fixture-only" not in json.dumps(providers)
        assert (
            restored.providers.model_config({"provider": "api-only", "modelId": "test-model"})["model_kwargs"][
                "api_key"
            ]
            == "local-fixture-only"
        )
        assert (
            next(item for item in restored.invoke("listModels") if item["provider"] == "api-only")["id"] == "test-model"
        )
        assert not {"oauth", "accountQuota"} & restored.invoke("getCapabilityStatus")["features"].keys()
        for method in ("startProviderLogin", "cancelProviderLogin", "respondProviderLogin", "getQuota"):
            with pytest.raises(ValueError, match="not supported"):
                restored.invoke(method, {"loginId": "removed", "providerId": "removed"})
    finally:
        restored.close()


def test_saved_model_options_reach_actual_request_and_override_stale_frontend(tmp_path):
    received = []

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            payload = json.dumps(
                {
                    "id": "local-response",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "gpt-4o-mini",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": "ok",
                                "tool_calls": [
                                    {
                                        "id": "local-call",
                                        "type": "function",
                                        "function": {"name": "bash", "arguments": '{"command": "echo verified"}'},
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service = DesktopService(tmp_path / "state")
    try:
        address = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        service.providers.configure(
            {
                "id": "local",
                "name": "Local",
                "template": "custom",
                "baseUrl": address,
                "fullUrl": True,
                "api": "openai-completions",
                "models": [
                    {
                        "id": "gpt-4o-mini",
                        "name": "Display name",
                        "reasoning": True,
                        "maxTokens": 512,
                        "advanced": {
                            "temperature": 0,
                            "topP": 0.8,
                            "toolCallLimit": 37,
                            "reasoningParameter": "reasoning_effort",
                            "reasoningValues": ["default", "off", "low", "high"],
                        },
                    }
                ],
            }
        )
        meta = service.invoke(
            "createSession", {"options": {"cwd": str(tmp_path), "provider": "local", "modelId": "gpt-4o-mini"}}
        )
        value = service.sessions.get(meta["sessionId"])
        value["meta"]["thinkingLevel"] = "high"
        value["modelOptions"] = {"temperature": "1.9", "toolCallLimit": "99"}
        config = service.sessions.config(value)
        assert config["agent"]["desktop_tool_call_limit"] == 37
        model = get_model(config=config["model"])
        model.query([{"role": "user", "content": "Hello"}])
        path, request = received[-1]
        assert path == "/v1/chat/completions"
        assert request["temperature"] == 0 and request["top_p"] == 0.8 and request["max_tokens"] == 512
        assert request["reasoning_effort"] == "high"
        provider = next(row for row in service.providers.list() if row["id"] == "local")
        assert provider["fullUrl"] and provider["requestUrl"] == address
        assert service.providers.models()[0]["label"] == "gpt-4o-mini"
        assert service.providers.models()[0]["thinkingLevels"] == ["default", "off", "low", "high"]
        with pytest.raises(ValueError, match="密钥"):
            service.providers.upstream({"baseUrl": "https://example.invalid/v1"})
    finally:
        service.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_custom_parameter_paths_and_url_validation():
    kwargs = {}
    apply_reasoning(kwargs, "reasoning.effort", "high")
    assert kwargs == {"reasoning": {"effort": "high"}}
    for name in ("api_key", "messages", "headers.Authorization", "reasoning..effort"):
        with pytest.raises(ValueError):
            ModelOptions(reasoningParameter=name)
    assert endpoint_base("https://example.com/v1/responses", "openai-responses", True) == "https://example.com/v1"
    with pytest.raises(ValueError):
        endpoint_base("https://example.com/v1?key=secret", "openai-completions")


@pytest.mark.parametrize(
    ("address", "custom", "expected"),
    [("", False, "none"), ("https://api.openai.com/v1", True, "none"), ("https://relay.invalid/v1", True, "off")],
)
def test_openai_thinking_off_uses_the_effective_endpoint(tmp_path, address, custom, expected):
    """Built-in OpenAI uses its native off value; compatible relays retain their configured semantics."""
    from vera.desktop.providers import Providers
    from vera.desktop.store import DesktopStore

    store = DesktopStore(tmp_path)
    store.save(
        "settings",
        "providers",
        {
            "openai": {
                "id": "openai",
                "name": "OpenAI",
                "custom": custom,
                "baseUrl": address,
                "api": "openai-completions",
                "models": [{"id": "gpt-5.1", "reasoning": True}],
            }
        },
    )
    providers = Providers(store)
    reference = {"provider": "openai", "modelId": "gpt-5.1"}
    options = ModelOptions().model_dump(by_alias=True)
    assert providers.reasoning_kwargs(reference, "off", options) == {"reasoning_effort": expected}
    assert providers.reasoning_kwargs(reference, "default", options) == {}
    assert providers.reasoning_kwargs(reference, "high", options) == {"reasoning_effort": "high"}


def test_invalid_provider_request_is_not_retried():
    """Regression: a deterministic HTTP 400 previously left the desktop waiting for minutes."""
    from litellm.exceptions import BadRequestError

    calls = []

    class Peer(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers["Content-Length"])))
            payload = b'{"error":{"message":"Invalid max_tokens value","type":"invalid_request_error"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Peer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        model = get_model(
            config={
                "model_name": "openai/qa-bad-request",
                "cost_tracking": "tokens",
                "model_kwargs": {
                    "api_key": "local-only",
                    "api_base": f"http://127.0.0.1:{server.server_port}",
                    "num_retries": 0,
                },
            }
        )
        with pytest.raises(BadRequestError, match="Invalid max_tokens"):
            model.query([{"role": "user", "content": "Hello"}])
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
