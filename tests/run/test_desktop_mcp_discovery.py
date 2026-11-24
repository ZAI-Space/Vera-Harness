"""Local MCP discovery is bounded, read-only and requires an explicit import choice."""

import json

import pytest

from vera.desktop.mcp_discovery import discover, load


def test_known_configs_discovered_without_running_commands_or_returning_secrets(tmp_path):
    workspace, home = tmp_path / "workspace", tmp_path / "home"
    workspace.mkdir()
    (home / ".cursor").mkdir(parents=True)
    project = {"mcpServers": {"qa-time": {"command": "missing-do-not-execute", "args": ["--test"]}}}
    (workspace / ".mcp.json").write_text(json.dumps(project), encoding="utf-8")
    private = {"mcpServers": {"private": {"url": "https://example.com/mcp", "env": {"API_KEY": "local-secret"}}}}
    (home / ".cursor/mcp.json").write_text(json.dumps(private), encoding="utf-8")
    (home / ".claude.json").write_text("invalid", encoding="utf-8")
    result = discover(workspace, home)
    assert len(result) == 3 and "local-secret" not in json.dumps(result)
    assert any(row.get("error") for row in result)
    loaded = load(workspace, "project-mcp", home)
    assert loaded["mcpServers"]["qa-time"]["cwd"] == str(workspace)
    assert load(workspace, "user-cursor", home) == private
    assert json.loads((workspace / ".mcp.json").read_text()) == project
    with pytest.raises(ValueError, match="扫描"):
        load(workspace, "../../other", home)
    (workspace / ".mcp.json").write_bytes(b" " * 1_048_577)
    with pytest.raises(ValueError, match="1 MiB"):
        load(workspace, "project-mcp", home)


def test_loading_a_removed_scan_result_reports_an_actionable_error(tmp_path):
    """A selected config may disappear after scanning; loading must remain a user error."""
    workspace, home = tmp_path / "workspace", tmp_path / "home"
    workspace.mkdir()
    path = workspace / ".mcp.json"
    path.write_text(json.dumps({"mcpServers": {"local": {"command": "do-not-run"}}}), encoding="utf-8")
    assert discover(workspace, home)[0]["id"] == "project-mcp"
    path.unlink()
    with pytest.raises(ValueError, match="无法读取本地 MCP 配置"):
        load(workspace, "project-mcp", home)
    path.mkdir()
    with pytest.raises(ValueError, match="无法读取本地 MCP 配置"):
        load(workspace, "project-mcp", home)
