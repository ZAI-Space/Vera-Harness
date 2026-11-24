"""Discover known local MCP JSON files without starting servers or changing configuration."""

import json
from pathlib import Path


def candidates(workspace: Path, home: Path | None = None) -> dict[str, Path]:
    """Return known user/project locations instead of recursively scanning the disk."""
    home = home or Path.home()
    return {
        "project-mcp": workspace / ".mcp.json",
        "project-cursor": workspace / ".cursor/mcp.json",
        "project-vscode": workspace / ".vscode/mcp.json",
        "user-cursor": home / ".cursor/mcp.json",
        "user-claude": home / ".claude.json",
    }


def read_config(path: Path) -> dict:
    """Read bounded JSON, retaining transport options for explicit review before import."""
    if path.stat().st_size > 1_048_576:
        raise ValueError("本地 MCP 配置超过 1 MiB，请手动复制所需服务。")
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    servers = document.get("mcpServers", document.get("servers")) if isinstance(document, dict) else None
    if not isinstance(servers, dict) or not servers or not all(isinstance(value, dict) for value in servers.values()):
        raise ValueError("配置中没有有效的 mcpServers 或 servers 对象。")
    normalized = {}
    for name, server in servers.items():
        entry = dict(server)
        if entry.get("type") in {"stdio", "http"}:
            entry.pop("type")
        if entry.get("command") and not entry.get("cwd"):
            entry["cwd"] = str(path.parent)
        normalized[name] = entry
    return {"mcpServers": normalized}


def discover(workspace: Path, home: Path | None = None) -> list[dict]:
    """List names and paths only; read configuration only after explicit user selection."""
    result = []
    for identifier, path in candidates(workspace, home).items():
        if not path.is_file():
            continue
        try:
            config = read_config(path)
        except (ValueError, OSError):
            result.append(
                {"id": identifier, "path": str(path), "names": [], "error": "无法读取有效 JSON，请手动检查此文件。"}
            )
        else:
            result.append({"id": identifier, "path": str(path), "names": list(config["mcpServers"])})
    return result


def load(workspace: Path, identifier: str, home: Path | None = None) -> dict:
    """Load a known location; arbitrary paths and process execution are unsupported."""
    path = candidates(workspace, home).get(identifier)
    if path is None:
        raise ValueError("请选择扫描到的本地 MCP 配置。")
    try:
        return read_config(path)
    except OSError:
        raise ValueError("无法读取本地 MCP 配置，请检查文件是否存在且可读取。") from None
