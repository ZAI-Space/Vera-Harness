"""Exercise catalog HTTP, validated Git snapshots, selection and real MCP sessions without mocks."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from minisweagent.markets.mcp import MCPRegistry, MCPServices, merge_services
from minisweagent.markets.skills import SkillMarket, install_skill_snapshot, remove_market_skill
from minisweagent.plugins.source import open_source
from minisweagent.runtime import open_agent_runtime
from minisweagent.terminal.session import TerminalSession
from minisweagent.tools import ToolError, ToolRegistry
from minisweagent.tools.mcp import open_mcp_tools, parse_mcp_servers
from minisweagent.tools.skills import SkillConfig, discover_skills
from tests.run.test_mcp_tools import ECHO_CALL, http_server  # noqa: F401
from tests.run.test_skill_tools import run_cli, write_skill
from tests.run.test_terminal_runtime import runtime_profile


@pytest.fixture
def catalog_server():
    state = {
        "server": {
            "name": "io.example/fixture",
            "version": "1.2.3",
            "description": "Fixture service",
            "packages": [
                {
                    "registryType": "npm",
                    "identifier": "@example/fixture",
                    "version": "1.2.3",
                    "transport": {"type": "stdio"},
                    "packageArguments": [{"type": "positional", "name": "workspace", "isRequired": True}],
                    "environmentVariables": [{"name": "VERA_OPTIONAL_FIXTURE_TOKEN"}],
                }
            ],
        },
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            address = urlsplit(self.path)
            state["requests"].append((unquote(address.path), parse_qs(address.query)))
            if address.path == "/api/search":
                value = {
                    "skills": [{"id": "example/repository/good-skill", "name": "good-skill"}, {"id": "../../unsafe"}]
                }
            elif address.path == "/servers":
                value = {"servers": [{"server": state["server"]}], "metadata": {"nextCursor": "next-page"}}
            else:
                value = {"server": state["server"]}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        state["url"] = f"http://127.0.0.1:{server.server_port}"
        try:
            yield state
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_latest_registry_search_inspection_inputs_and_private_service_selection(tmp_path, catalog_server):
    registry = MCPRegistry(catalog_server["url"])
    page = registry.search("fixture", cursor="old", limit=4)
    assert page["next_cursor"] == "next-page"
    assert catalog_server["requests"][0][1] == {
        "search": ["fixture"],
        "version": ["latest"],
        "limit": ["4"],
        "cursor": ["old"],
    }
    preview = registry.preview("io.example/fixture")
    assert preview["required_inputs"] == ["workspace"]
    assert preview["config"]["args"] == ["-y", "@example/fixture@1.2.3"]
    store = MCPServices(tmp_path / "services")
    assert store.list() == {} and not store.directory.exists()
    with pytest.raises(ToolError, match="required inputs"):
        store.add(preview)
    preview = registry.preview("io.example/fixture", inputs={"workspace": str(tmp_path)})
    store.add(preview)
    with pytest.raises(ToolError, match="already installed"):
        store.add(preview)
    config = {"mcp_services": {"directory": str(store.directory)}}
    assert merge_services(config)["mcp_servers"] == {}
    session = TerminalSession(config, tmp_path)
    assert session.catalog("/mcp") == [{"name": "fixture", "description": "Configured MCP service"}]
    session.process("/mcp fixture")
    assert merge_services(session.runtime_config())["mcp_servers"]["fixture"]["args"][-1] == str(tmp_path)
    explicit = config | {
        "mcp_servers": {"fixture": {"url": "https://explicit.example/mcp"}},
        "mcp_selection": ["fixture"],
    }
    assert merge_services(explicit)["mcp_servers"]["fixture"]["url"] == "https://explicit.example/mcp"
    store.remove("fixture")
    assert store.list() == {}


def test_remote_market_service_runs_only_when_selected_and_uses_real_sdk(tmp_path, catalog_server, http_server):
    url, requests, _ = http_server
    catalog_server["server"]["remotes"] = [{"type": "streamable-http", "url": url + "/mcp"}]
    store = MCPServices(tmp_path / "services")
    store.add(MCPRegistry(catalog_server["url"]).preview("io.example/fixture"))
    config = runtime_profile(tmp_path) | {"mcp_services": {"directory": str(store.directory)}}
    with open_agent_runtime(config) as runtime:
        assert runtime.agent.tool_registry is None and not requests
    config["mcp_selection"] = ["fixture"]
    with open_agent_runtime(config) as runtime:
        result = runtime.agent.tool_registry.execute(ECHO_CALL)
        assert json.loads(result["output"])["text"] == "hello from MCP"
    assert requests


def test_registry_rejects_unpinned_unsafe_or_unsupported_transports_and_secret_argv(catalog_server):
    registry = MCPRegistry(catalog_server["url"])
    package = catalog_server["server"]["packages"][0]
    package["packageArguments"][0]["isSecret"] = True
    with pytest.raises(ToolError, match="Secret command-line"):
        registry.preview("io.example/fixture")
    package["packageArguments"] = []
    package["version"] = "latest"
    with pytest.raises(ToolError, match="explicitly versioned"):
        registry.preview("io.example/fixture")
    package["version"] = "1"
    with pytest.raises(ToolError, match="explicitly versioned"):
        registry.preview("io.example/fixture")
    package["version"] = "--untrusted-option"
    with pytest.raises(ToolError, match="explicitly versioned"):
        registry.preview("io.example/fixture")
    catalog_server["server"]["packages"] = [{"registryType": "oci", "identifier": "arbitrary"}]
    with pytest.raises(ToolError, match="No supported"):
        registry.preview("io.example/fixture")
    with pytest.raises(ToolError):
        MCPRegistry("https://user:password@example.com").search()


def test_unselected_or_corrupt_market_settings_do_not_change_normal_runtime(tmp_path):
    store = MCPServices(tmp_path / "settings")
    store.directory.mkdir()
    store.path.write_text("{invalid JSON", encoding="utf-8")
    config = {"mcp_services": {"directory": str(store.directory)}}
    assert merge_services(config)["mcp_servers"] == {}
    session = TerminalSession(config, tmp_path)
    assert session.catalog("/subagent") == []
    with pytest.raises(ValueError):
        merge_services(config, catalog=True)


def test_header_auth_uses_environment_names_and_rejects_protocol_overrides(catalog_server):
    catalog_server["server"]["remotes"] = [
        {
            "type": "streamable-http",
            "url": "https://service.example/mcp",
            "headers": [{"name": "X-Api-Key", "isRequired": True}, {"name": "Authorization"}],
        }
    ]
    plan = MCPRegistry(catalog_server["url"]).preview("io.example/fixture", header_env={"X-Api-Key": "MY_API_KEY"})
    assert plan["config"]["headers_from"] == {"X-Api-Key": "MY_API_KEY"}
    assert "bearer_token_env" not in plan["config"]
    assert "MY_API_KEY" in plan["missing_environment"]
    for config in (
        {"url": "https://example.com", "headers_from": {"Host": "TOKEN"}},
        {"url": "http://example.com", "headers_from": {"X-Key": "TOKEN"}},
        {"command": "python", "optional_env_from": ["not a variable"]},
    ):
        with pytest.raises(ToolError):
            parse_mcp_servers({"fixture": config})


def test_optional_stdio_environment_and_custom_http_auth_use_real_mcp_sessions(http_server):
    from tests.run.test_mcp_tools import FIXTURE_PATH

    previous = {name: os.environ.get(name) for name in ("MCP_TEST_ALLOWED", "VERA_HTTP_AUTH")}
    os.environ["MCP_TEST_ALLOWED"] = "allowed-fixture"
    os.environ["VERA_HTTP_AUTH"] = "Bearer private-fixture"
    try:
        configs = parse_mcp_servers(
            {
                "fixture": {
                    "command": sys.executable,
                    "args": [str(FIXTURE_PATH)],
                    "optional_env_from": ["MCP_TEST_ALLOWED", "VERA_MISSING_OPTIONAL_VARIABLE"],
                },
                "remote": {"url": http_server[0] + "/mcp", "headers_from": {"Authorization": "VERA_HTTP_AUTH"}},
            }
        )
        registry = ToolRegistry()
        with open_mcp_tools(registry, configs):
            assert json.loads(registry.execute(ECHO_CALL)["output"])["allowed"] is True
            assert registry.execute(ECHO_CALL | {"tool": "mcp_remote_echo"})["returncode"] == 0
        assert any(header == b"Bearer private-fixture" for _, header in http_server[1])
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_skill_market_search_snapshot_assets_discovery_and_safe_removal(tmp_path, catalog_server):
    market = SkillMarket(catalog_server["url"])
    assert market.search("good") == [
        {
            "id": "example/repository/good-skill",
            "name": "good-skill",
            "repository": "https://github.com/example/repository",
            "installs": 0,
        }
    ]
    source_root = tmp_path / "source"
    write_skill(source_root / "skills", "good-skill", "Downloaded instruction")
    support = source_root / "skills" / "good-skill" / "references"
    (support / "usage.md").write_text("Support content", encoding="utf-8")
    destination = tmp_path / "installed"
    with open_source(str(source_root)) as source:
        receipt = install_skill_snapshot(source, "good-skill", destination)
        assert receipt["files"] == 3 and "Downloaded instruction" in receipt["instructions"]
        with pytest.raises(ToolError, match="already installed"):
            install_skill_snapshot(source, "good-skill", destination)
    project = tmp_path / "project"
    project.mkdir()
    discovered = discover_skills(SkillConfig(directories=[destination]), project)
    assert discovered["good-skill"].view("references/usage.md")["content"] == "Support content"
    attachment = destination / "good-skill" / "references" / "usage.md"
    attachment.write_text("Local edit", encoding="utf-8")
    with pytest.raises(ToolError, match="local changes"):
        remove_market_skill("good-skill", destination)
    assert attachment.read_text() == "Local edit"
    attachment.write_text("Support content", encoding="utf-8")
    remove_market_skill("good-skill", destination)
    assert not (destination / "good-skill").exists()
    with pytest.raises(ToolError):
        remove_market_skill("../project", destination)


def test_market_cli_help_never_starts_a_model_or_service(tmp_path):
    for command in ("mcp", "skills"):
        result = run_cli(tmp_path, "minisweagent.run.utilities.mini_extra", command, "--help")
        assert "search" in result.stdout and ("add" if command == "mcp" else "install") in result.stdout
