"""Adapt enabled plugin declarations to Vera's existing capability modules."""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from vera import global_config_dir
from vera.plugins.manager import PluginManager
from vera.plugins.manifest import load_bundle
from vera.plugins.source import PluginError
from vera.tools.skills import Skill, SkillConfig


class PluginConfig(BaseModel):
    """Select explicitly enabled user packages; project config cannot approve a disabled package."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    directory: Path = global_config_dir / "plugins"
    names: list[str] | None = None


@dataclass
class PluginRuntime:
    """A run-local config copy and namespaced skills; no state is written during loading."""

    config: dict
    skills: dict[str, Skill] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)


def load_plugins(config: dict) -> PluginRuntime:
    """Load approved immutable versions, rejecting capability collisions before model startup.

    MCP commands connect later through open_mcp_tools and retain SandboxConfig's
    external-tool checks. No package can change model, environment or agent settings.
    The input config is not mutated; disabled plugins never contribute capabilities.
    """
    result = PluginRuntime(deepcopy(config))
    try:
        settings = PluginConfig.model_validate(config.get("plugins", {}))
    except ValidationError:
        raise PluginError("Invalid plugins config; use enabled, directory and optional names.") from None
    if not settings.enabled:
        return result
    manager = PluginManager(settings.directory)
    installed = manager.list_plugins()
    selected = (
        settings.names
        if settings.names is not None
        else [name for name, plugin in installed.items() if plugin["enabled"]]
    )
    for name in dict.fromkeys(selected):
        if name not in installed or not installed[name]["enabled"]:
            raise PluginError(f"Plugin {name!r} must be installed and explicitly enabled.")
        plugin = installed[name]
        record = plugin["versions"][plugin["active"]]
        bundle = load_bundle(manager.package(record))
        servers = result.config.setdefault("mcp_servers", {})
        subagents = result.config.setdefault("subagents", {})
        if not isinstance(servers, dict) or not isinstance(subagents, dict):
            raise PluginError("Plugin integration requires mcp_servers and subagents mappings.")
        roles = subagents.setdefault("roles", {})
        if not isinstance(roles, dict):
            raise PluginError("Plugin integration requires a subagents.roles mapping.")
        for target, additions in ((servers, bundle.servers), (roles, bundle.roles), (result.skills, bundle.skills)):
            if collision := target.keys() & additions.keys():
                raise PluginError(f"Plugin capability name collision: {sorted(collision)}.")
        servers.update({key: server.model_dump(exclude_none=True) for key, server in bundle.servers.items()})
        roles.update({key: role.model_dump(exclude_none=True) for key, role in bundle.roles.items()})
        result.skills.update(bundle.skills)
        result.versions[name] = record["digest"]
    try:
        skills = SkillConfig.model_validate(config.get("skills", {}))
    except ValidationError:
        raise PluginError("Invalid skills config.") from None
    result.skills = {
        name: skill for name, skill in result.skills.items() if skills.enabled and name not in skills.disabled
    }
    return result
