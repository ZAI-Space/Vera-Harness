"""Validate portable, Codex-compatible and Vera plugin declarations without executing code."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from vera.agents.subagents import SubagentConfig, SubagentRole
from vera.plugins.source import PluginError, package_path
from vera.tools import ToolError
from vera.tools.mcp import MCPServerConfig, mcp_tool_name, parse_mcp_servers
from vera.tools.skills import Skill, discover_skill_roots


def read_json(path: Path) -> dict:
    """Read a bounded JSON object and report a package error instead of leaking input values."""
    try:
        if path.stat().st_size > 1024 * 1024:
            raise PluginError(f"JSON file exceeds 1 MiB: {path.name}.")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise PluginError(f"Expected a JSON object: {path.name}.")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PluginError(f"Cannot read {path.name}: {type(error).__name__}.") from None


class PluginManifest(BaseModel):
    """Stable package identity; presentation metadata is retained in the original manifest."""

    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=48)
    version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$")
    description: str = Field(min_length=1, max_length=1024)


@dataclass(frozen=True)
class PluginSkill(Skill):
    """Expose a namespaced skill while validating the original on-disk skill identity."""

    source: Skill

    def view(self, file_path: str | None = None) -> dict:
        """Read through the existing Skill validator and expose the plugin-qualified name."""
        return self.source.view(file_path) | {"name": self.name}


def namespace(plugin: str, name: str, limit: int = 64) -> str:
    """Make a stable, bounded identifier while retaining readable plugin ownership."""
    value = f"{plugin}-{name}"
    return value if len(value) <= limit else f"{value[: limit - 13]}-{sha256(value.encode()).hexdigest()[:12]}"


@dataclass(frozen=True)
class PluginBundle:
    """Validated declarations ready for existing Skills, MCP and Subagent runtime adapters."""

    manifest: PluginManifest
    skills: dict[str, Skill]
    servers: dict[str, MCPServerConfig]
    roles: dict[str, SubagentRole]

    def describe(self) -> dict:
        """Return reviewable capability names and command/auth requirements, without secret values."""
        return self.manifest.model_dump() | {
            "skills": list(self.skills),
            "mcp_servers": {name: server.model_dump(exclude_none=True) for name, server in self.servers.items()},
            "subagents": list(self.roles),
        }


def _servers(root: Path, value: object) -> dict[str, MCPServerConfig]:
    if isinstance(value, str):
        value = read_json(package_path(root, value))
    if not isinstance(value, dict):
        raise PluginError("mcpServers must be a mapping or a package-relative JSON file.")
    value = value.get("mcpServers", value)
    if not isinstance(value, dict):
        raise PluginError("mcpServers must be a mapping.")
    normalized = {}
    for name, original in value.items():
        if name == "$schema":
            continue
        if not isinstance(original, dict):
            raise PluginError("Each MCP server must be an object.")
        server = original.copy()
        transport = server.pop("type", None)
        if transport is not None and transport != ("stdio" if server.get("command") else "streamable-http"):
            if not (transport == "http" and server.get("url")):
                raise PluginError("Plugins support MCP stdio and Streamable HTTP transports.")
        if "env" in server:
            environment = server.pop("env")
            if not isinstance(environment, dict) or any(value != f"${{{key}}}" for key, value in environment.items()):
                raise PluginError("Plugin MCP env only supports NAME: ${NAME}; use env_from for secret forwarding.")
            inherited = server.get("env_from", [])
            if not isinstance(inherited, list) or any(not isinstance(name, str) for name in inherited):
                raise PluginError("env_from must be a list of environment variable names.")
            server["env_from"] = list(dict.fromkeys([*inherited, *environment]))
        if "headers" in server:
            headers = server.pop("headers")
            token = headers.get("Authorization", "") if isinstance(headers, dict) else ""
            match = re.fullmatch(r"Bearer \$\{([A-Za-z_][A-Za-z0-9_]*)\}", token) if isinstance(token, str) else None
            if not match or len(headers) != 1 or "bearer_token_env" in server:
                raise PluginError("Plugin HTTP headers support only Authorization: Bearer ${ENV_NAME}.")
            server["bearer_token_env"] = match[1]
        for key in ("command", "cwd"):
            if isinstance(server.get(key), str):
                server[key] = _expand_root(server[key], root)
        if isinstance(server.get("args"), list):
            server["args"] = [
                _expand_root(argument, root) if isinstance(argument, str) else argument for argument in server["args"]
            ]
        if server.get("command"):
            server.setdefault("cwd", str(root))
        normalized[name] = server
    try:
        return parse_mcp_servers(normalized)
    except ToolError as error:
        raise PluginError(str(error)) from None


def _expand_root(value: str, root: Path) -> str:
    for variable in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "CODEX_PLUGIN_ROOT"):
        marker = f"${{{variable}}}"
        # Extended Windows paths require native separators; author manifests use POSIX paths.
        if marker in value and str(root).startswith("\\\\?\\"):
            value = value.replace("/", "\\")
        value = value.replace(marker, str(root))
    return value


def load_bundle(root: Path) -> PluginBundle:
    """Validate a complete installed package and namespace its capabilities.

    Portable plugin.json takes precedence over compatibility manifests. Unsupported
    execution surfaces (hooks, commands, hosted Apps) fail explicitly. Tools are
    contributed through the existing MCP adapter, not arbitrary Python imports.
    """
    candidates = ("plugin.json", ".vera-plugin/plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
    selected = next((path for path in candidates if package_path(root, path).is_file()), None)
    if selected is None:
        raise PluginError("Missing plugin.json or .vera-plugin/.codex-plugin/.claude-plugin/plugin.json.")
    original = read_json(package_path(root, selected))
    try:
        manifest = PluginManifest.model_validate(original)
        extensions = original.get("extensions", {})
        if not isinstance(extensions, dict):
            raise PluginError("extensions must be an object.")
        settings = original
        if selected == "plugin.json":
            settings = extensions.get("com.openai", {})
            if "com.openai" not in extensions and package_path(root, ".codex-plugin/plugin.json").is_file():
                settings = read_json(package_path(root, ".codex-plugin/plugin.json"))
        if not isinstance(settings, dict):
            raise PluginError("Plugin compatibility settings must be an object.")
        for unsupported in ("apps", "hooks", "commands", "agents"):
            if settings.get(unsupported) or original.get(unsupported):
                raise PluginError(f"Unsupported plugin capability {unsupported!r}; use Skills, MCP or Vera subagents.")
        for default in ("hooks/hooks.json", ".app.json"):
            if package_path(root, default).is_file() and any(read_json(package_path(root, default)).values()):
                raise PluginError(f"Unsupported plugin capability file: {default}.")
        skills_value = "./skills" if selected == "plugin.json" else settings.get("skills", "./skills")
        if isinstance(skills_value, str):
            skills_value = [skills_value]
        if not isinstance(skills_value, list) or any(not isinstance(path, str) for path in skills_value):
            raise PluginError("skills must be a package-relative directory or list of directories.")
        roots = [package_path(root, path) for path in skills_value]
        if selected != "plugin.json" and settings.get("skills") and any(not directory.is_dir() for directory in roots):
            raise PluginError("Declared skills directory does not exist.")
        skills = discover_skill_roots(roots)
        server_value = None if selected == "plugin.json" else settings.get("mcpServers")
        if server_value is None:
            default = "mcp.json" if selected == "plugin.json" else ".mcp.json"
            server_value = default if package_path(root, default).is_file() else {}
        servers = _servers(root, server_value)
        vera = extensions.get("vera", {}) if selected == "plugin.json" else original
        if not isinstance(vera, dict):
            raise PluginError("extensions.vera must be an object.")
        roles_value = vera.get("subagents", {})
        if isinstance(roles_value, str):
            roles_value = read_json(package_path(root, roles_value))
        roles = SubagentConfig(roles=roles_value).roles
    except (ValidationError, ToolError) as error:
        if isinstance(error, ValidationError):
            message = "; ".join(
                f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}" for issue in error.errors(include_input=False)
            )
        else:
            message = str(error)
        raise PluginError(f"Invalid plugin: {message}") from None
    server_names = {name: namespace(manifest.name, name, 32) for name in servers}
    skill_names = {name: namespace(manifest.name, name) for name in skills}
    result_roles = {}
    for name, role in roles.items():
        if missing := set(role.skills) - skills.keys():
            raise PluginError(f"Subagent {name!r} references unknown plugin skills: {sorted(missing)}.")
        tools = []
        for tool in role.tools:
            if tool.startswith("mcp:"):
                parts = tool[4:].split("/", 1)
                if len(parts) != 2 or parts[0] not in servers or not parts[1]:
                    raise PluginError(f"Invalid plugin MCP tool reference: {tool!r}.")
                tool = mcp_tool_name(server_names[parts[0]], parts[1])
            tools.append(tool)
        result_roles[namespace(manifest.name, name, 48)] = role.model_copy(
            update={"skills": [skill_names[skill] for skill in role.skills], "tools": tools}
        )
    return PluginBundle(
        manifest,
        {
            skill_names[name]: PluginSkill(skill_names[name], skill.description, skill.directory, skill)
            for name, skill in skills.items()
        },
        {server_names[name]: server for name, server in servers.items()},
        result_roles,
    )
