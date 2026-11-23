"""Exercise discovery over real HTTP, including protocol headers and safe failures."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from vera.desktop.providers import Providers
from vera.desktop.store import DesktopStore


@pytest.fixture
def model_endpoint():
    """Serve a local provider peer without replacing requests or production methods."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requests.append((self.path, dict(self.headers)))
            status = {"/models": 404, "/denied/models": 401, "/limited/models": 429}.get(self.path, 200)
            body = (
                {"models": [{"name": "models/native", "displayName": "Native"}]}
                if self.path.startswith("/v1beta")
                else {"data": [{"id": "chat"}]}
            )
            if self.path.startswith("/malformed"):
                body = {"data": None}
            if self.path.startswith("/capabilities"):
                body = {
                    "data": [
                        {
                            "id": "deepseek-flash",
                            "context_window": 131072,
                            "max_output_tokens": 8192,
                            "input_modalities": ["text"],
                            "effort": {"supported_levels": ["low", "high"]},
                        }
                    ]
                }
            payload = b"not json" if self.path.startswith("/html") else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    ("protocol", "header", "path", "model"),
    [
        ("openai-completions", "Authorization", "/v1/models", "chat"),
        ("anthropic-messages", "x-api-key", "/v1/models", "chat"),
        ("google-generative-ai", "x-goog-api-key", "/v1beta/models", "native"),
    ],
)
def test_discovery_uses_protocol_auth_and_version_fallback(tmp_path, model_endpoint, protocol, header, path, model):
    endpoint, received = model_endpoint
    result = Providers(DesktopStore(tmp_path)).upstream(
        {"baseUrl": endpoint, "api": protocol, "apiKey": "local-discovery-key"}
    )
    assert result["models"][0]["id"] == model
    assert received[-1][0] == path
    assert received[-1][1][header] == ("Bearer " if header == "Authorization" else "") + "local-discovery-key"
    if protocol == "anthropic-messages":
        assert received[-1][1]["anthropic-version"] == "2023-06-01"


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/denied", "鉴权失败"),
        ("/limited", "限流"),
        ("/html", "有效 JSON"),
        ("/malformed", "列表格式"),
    ],
)
def test_discovery_reports_safe_actionable_failures(tmp_path, model_endpoint, path, message):
    endpoint, _ = model_endpoint
    with pytest.raises(ValueError, match=message) as failure:
        Providers(DesktopStore(tmp_path)).upstream({"baseUrl": endpoint + path, "apiKey": "local-discovery-key"})
    assert "local-discovery-key" not in str(failure.value)
    assert endpoint not in str(failure.value)


def test_reported_capabilities_override_stale_catalog_and_reject_unsupported_configuration(tmp_path, model_endpoint):
    """Regression: live QA found SDK output limits sent as invalid DeepSeek max_tokens."""
    endpoint, _ = model_endpoint
    providers = Providers(DesktopStore(tmp_path))
    address = endpoint + "/capabilities"
    model = providers.upstream({"baseUrl": address})["models"][0]
    assert model["contextWindow"] == 131072 and model["maxTokens"] == 8192
    assert model["imageInput"] is False and model["reasoningValues"] == ["default", "off", "low", "high"]
    base = {"id": "capabilities", "baseUrl": address, "api": "openai-completions"}
    for override in ({"contextWindow": 1000000}, {"maxTokens": 1000000}, {"imageInput": True}):
        with pytest.raises(ValueError):
            providers.configure(base | {"models": [{"id": "deepseek-flash", **override}]})
    providers.configure(base | {"models": [{"id": "deepseek-flash", "contextWindow": 131072, "maxTokens": 8192}]})
    assert (
        providers.model_config({"provider": "capabilities", "modelId": "deepseek-flash"})["model_kwargs"]["max_tokens"]
        == 8192
    )
