"""Read publisher presentation metadata from the already fetched marketplace revision."""

import base64
import json
from pathlib import PurePosixPath

from vera.plugins.source import PluginError, Source, relative_path


def package_presentation(
    source: Source, path: str, files: set[str], *, contents: dict[str, bytes] | None = None
) -> dict:
    """Return declared descriptions, capabilities and a bounded image; never run package code.

    Only files inside the package and supplied Git revision are read. Unsupported
    execution surfaces remain visible as compatibility information in the market.
    """
    root = PurePosixPath(path)
    manifests = ("plugin.json", ".vera-plugin/plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
    manifest = next((str(root / name) for name in manifests if str(root / name) in files), None)
    if manifest is None:
        return {}
    try:
        value = json.loads(source.read_file(manifest) if contents is None else contents.get(manifest, b"null"))
        if not isinstance(value, dict):
            return {}
        interface = value.get("interface", {})
        interface = interface if isinstance(interface, dict) else {}
        result = {key: value[key] for key in ("description", "author", "version") if key in value}
        result.update(
            {
                key: interface[key]
                for key in ("displayName", "shortDescription", "longDescription", "category")
                if isinstance(interface.get(key), str)
            }
        )
        capabilities = []
        if value.get("skills") or any(file.startswith(str(root / "skills") + "/") for file in files):
            capabilities.append("Skills")
        if value.get("mcpServers") or str(root / ".mcp.json") in files or str(root / "mcp.json") in files:
            capabilities.append("MCP")
        if value.get("subagents"):
            capabilities.append("Subagents")
        result["capabilities"] = capabilities
        unsupported = [key for key in ("apps", "hooks", "commands", "agents") if value.get(key)]
        if unsupported:
            result["unsupported"] = "当前 Runtime 尚不支持此插件声明的能力：" + ", ".join(unsupported)
        for field in ("composerIcon", "logo"):
            icon = interface.get(field)
            if not isinstance(icon, str):
                continue
            icon_path = str(root / relative_path(icon))
            suffix = PurePosixPath(icon_path).suffix.lower()
            mime = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg"}.get(
                suffix
            )
            if mime and icon_path in files:
                try:
                    artwork = (
                        source.read_file(icon_path, limit=256 * 1024) if contents is None else contents.get(icon_path)
                    )
                except (PluginError, OSError):
                    continue
                if not artwork:
                    continue
                result["icon"] = f"data:{mime};base64," + base64.b64encode(artwork).decode()
                break
        return result
    except (PluginError, ValueError, UnicodeError, OSError):
        return {}


def marketplace_presentations(source: Source, paths: list[str], files: set[str]) -> dict[str, dict]:
    """Batch manifests and their referenced artwork at the same immutable revision."""
    manifests = {
        str(PurePosixPath(path) / name)
        for path in paths
        for name in (
            "plugin.json",
            ".vera-plugin/plugin.json",
            ".codex-plugin/plugin.json",
            ".claude-plugin/plugin.json",
        )
    } & files
    contents = source.read_files(list(manifests))
    icons = set()
    for path, content in contents.items():
        try:
            value = json.loads(content)
            interface = value.get("interface", {}) if isinstance(value, dict) else {}
            root = PurePosixPath(path).parent
            if root.name in {".vera-plugin", ".codex-plugin", ".claude-plugin"}:
                root = root.parent
            for field in ("composerIcon", "logo"):
                if isinstance(interface, dict) and isinstance(interface.get(field), str):
                    icon = str(root / relative_path(interface[field]))
                    if icon in files:
                        icons.add(icon)
        except (ValueError, PluginError):
            continue
    contents.update(source.read_files(list(icons), limit=256 * 1024))
    return {path: package_presentation(source, path, files, contents=contents) for path in paths}
