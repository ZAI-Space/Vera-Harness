"""Assemble the same agent capabilities for terminal and remote channel entry points."""

import json
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from minisweagent.agents import get_agent
from minisweagent.agents.subagents import SubagentConfig, register_subagent_tools
from minisweagent.environments import get_environment
from minisweagent.environments.sandbox import SandboxConfig, open_runtime
from minisweagent.models import get_model
from minisweagent.plugins import load_plugins
from minisweagent.tools import ToolError, make_tool_registry
from minisweagent.tools.mcp import open_mcp_tools, parse_mcp_servers
from minisweagent.tools.skills import Skill, SkillConfig, discover_skills, register_skill_tools
from minisweagent.tools.web import WebConfig, configure_web_tools


@dataclass
class AgentRuntime:
    """An assembled agent with run-scoped resources owned by open_agent_runtime."""

    agent: object
    skills: dict[str, Skill]
    workspace: Path
    policy: str
    plugin_versions: dict[str, str]
    mode: str | None


@contextmanager
def open_agent_runtime(config: dict, *, default_type: str = "interactive"):
    """Create model, environment and capability registrations; close MCP/sandbox on exit.

    The input is copied by the plugin adapter. No agent steps execute here. Callers
    own task selection, storage tracking and execution; configuration errors propagate.
    """
    plugins = load_plugins(config)
    config = plugins.config
    model_config = config.get("model", {})
    model = get_model(config=model_config)
    web = WebConfig.model_validate(config.get("web", {}))
    skill_config = SkillConfig.model_validate(config.get("skills", {}))
    subagents = SubagentConfig.model_validate(config.get("subagents", {}))
    sandbox = SandboxConfig.model_validate(config["sandbox"]) if "sandbox" in config else None
    servers = parse_mcp_servers(config.get("mcp_servers", {}))
    with ExitStack() as stack:
        environment_config = config.get("environment", {})
        mode = None
        has_web_tools = bool(web.search_provider or web.extract_provider)
        if sandbox is None:
            env = get_environment(environment_config, default_type="local")
        else:
            sandbox.check_external_tools(
                web_enabled=has_web_tools,
                stdio={name for name, server in servers.items() if server.command},
                http={name for name, server in servers.items() if server.url},
            )
            env, mode = stack.enter_context(open_runtime(sandbox, environment_config))
        catalog = discover_skills(skill_config, Path.cwd())
        if collision := catalog.keys() & plugins.skills.keys():
            raise ToolError(f"Plugin skill name collision: {sorted(collision)}.")
        catalog.update(plugins.skills)
        has_skill_tools = (
            bool(catalog)
            and callable(getattr(model, "bind_tool_registry", None))
            and getattr(model, "supports_tool_registry", True)
        )
        registry = None
        if has_web_tools or servers or has_skill_tools or subagents.roles:
            registry = make_tool_registry(env)
            configure_web_tools(registry, web)
            stack.enter_context(open_mcp_tools(registry, servers))
            if has_skill_tools:
                register_skill_tools(registry, catalog)
        agent = get_agent(model, env, config.get("agent", {}), default_type=default_type, tool_registry=registry)
        if subagents.roles:
            register_subagent_tools(registry, agent, subagents, model_config, catalog)
        workspace = sandbox.workspace if sandbox else Path(getattr(env.config, "cwd", "") or ".")
        policy = sandbox.model_dump_json() if sandbox else ""
        if plugins.versions:
            policy = json.dumps({"sandbox": policy, "plugins": plugins.versions}, sort_keys=True)
        yield AgentRuntime(agent, catalog, workspace.expanduser(), policy, plugins.versions, mode)
