"""Assemble the same agent capabilities for terminal and remote channel entry points."""

import json
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from vera.agents import get_agent, get_agent_class
from vera.agents.interactive import InteractiveAgent
from vera.agents.subagents import SubagentConfig, register_subagent_tools
from vera.environments import get_environment
from vera.environments.sandbox import SandboxConfig, open_runtime
from vera.environments.sandbox_profiles import resolve_sandbox_profile
from vera.markets.mcp import merge_services
from vera.models import get_model
from vera.modes.goals import register_goal_finish
from vera.modes.plan import plan_registry
from vera.permissions import PermissionsConfig, ReadOnlyEnvironment, register_readonly_finish
from vera.plugins import load_plugins
from vera.scheduler.tools import SchedulerSettings, register_scheduler_tools
from vera.tools import ToolError, make_tool_registry
from vera.tools.mcp import open_mcp_tools, parse_mcp_servers
from vera.tools.skills import Skill, SkillConfig, discover_skills, register_skill_tools
from vera.tools.web import WebConfig, configure_web_tools
from vera.user_context import DEFAULT_DIRECTORY as USER_CONTEXT_DIRECTORY
from vera.user_context import UserContext, apply_user_context


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
    workspace = config.get("sandbox", {}).get("workspace") or config.get("environment", {}).get("cwd")
    config = resolve_sandbox_profile(config, Path(workspace) if workspace else None)
    planning = config.get("run_mode") == "plan"
    if planning:
        # Planning is an explicit capability boundary, not a model-only instruction.
        config = config | {
            "plugins": {"enabled": False},
            "mcp_servers": {},
            "mcp_selection": [],
            "web": {},
            "subagents": {},
            "scheduler": {"enabled": False},
        }
        config = config | {
            "agent": config.get("agent", {})
            | {
                "system_template": "You are planning an implementation. Use project_files and project_read to inspect the workspace. "
                "Use plan_finish to save the complete Markdown plan and finish. No implementation or external actions are allowed."
            }
        }
    plugins = load_plugins(merge_services(config) if not planning else config)
    config = plugins.config
    scheduled = SchedulerSettings.model_validate(config.get("scheduler", {}))
    permissions = PermissionsConfig.model_validate(config.get("permissions", {}))
    readonly = permissions.mode == "read-only"
    if permissions.mode == "confirm":
        agent_config = config.get("agent", {})
        agent_type = get_agent_class(agent_config.get("agent_class", default_type))
        if not issubclass(agent_type, InteractiveAgent) or agent_config.get("mode", "confirm") != "confirm":
            raise ToolError("Confirmation permissions require an interactive agent in confirm mode.")
    if readonly:
        config["mcp_servers"] = {}
        agent_config = config.setdefault("agent", {})
        agent_config["instance_template"] = (
            agent_config.get("instance_template", "{{task}}")
            + "\nRead-only task: use task_finish to submit. Bash and external MCP are unavailable."
        )
    if "mcp_selection" in config:
        selected = config["mcp_selection"]
        if not isinstance(selected, list) or any(not isinstance(name, str) for name in selected):
            raise ToolError("mcp_selection must be a list of configured server names.")
        configured = config.get("mcp_servers", {})
        if not readonly and set(selected) - configured.keys():
            raise ToolError("Selected MCP services are no longer available.")
        config["mcp_servers"] = {name: server for name, server in configured.items() if name in selected}
    model_config = config.get("model", {})
    if planning or readonly or config.get("run_mode") == "goal":
        # These modes produce host-owned artifacts/decisions through a finish tool.
        model_config = model_config | {"allow_text_final": False}
    model = get_model(config=model_config)
    web = WebConfig.model_validate(config.get("web", {}))
    skill_config = SkillConfig.model_validate(config.get("skills", {}))
    subagents = SubagentConfig.model_validate(config.get("subagents", {}))
    if readonly:
        for role in subagents.roles.values():
            role.tools = [name for name in role.tools if name in {"web_search", "web_extract"}]
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
        if readonly:
            env = ReadOnlyEnvironment(env)
        workspace = sandbox.workspace if sandbox else Path(getattr(env.config, "cwd", "") or ".")
        catalog = discover_skills(skill_config, workspace.expanduser().resolve())
        if collision := catalog.keys() & plugins.skills.keys():
            raise ToolError(f"Plugin skill name collision: {sorted(collision)}.")
        catalog.update(plugins.skills)
        has_skill_tools = (
            bool(catalog)
            and callable(getattr(model, "bind_tool_registry", None))
            and getattr(model, "supports_tool_registry", True)
        )
        registry = None
        if planning:
            registry = plan_registry(workspace)
        elif (
            has_web_tools
            or servers
            or has_skill_tools
            or subagents.roles
            or readonly
            or scheduled.enabled
            or config.get("run_mode") == "goal"
        ):
            registry = make_tool_registry(env)
            configure_web_tools(registry, web)
            stack.enter_context(open_mcp_tools(registry, servers))
            if has_skill_tools:
                register_skill_tools(registry, catalog)
            if "mcp_selection" in config:
                # Explicit service selection also limits delegated MCP capabilities.
                available = {tool["function"]["name"] for tool in registry.definitions()}
                for role in subagents.roles.values():
                    role.tools = [name for name in role.tools if not name.startswith("mcp_") or name in available]
            if readonly:
                registry = registry.select(
                    [tool["function"]["name"] for tool in registry.definitions() if tool["function"]["name"] != "bash"]
                )
                register_readonly_finish(registry)
            if scheduled.enabled and not readonly:
                register_scheduler_tools(registry, scheduled, config, workspace, set(catalog))
            if config.get("run_mode") == "goal":
                register_goal_finish(registry)
        desktop_runtime = str(config.get("agent", {}).get("agent_class", "")).startswith(
            "vera.desktop.worker."
        ) or "desktop_workspace" in config.get("agent", {})
        if desktop_runtime and registry is not None and workspace:
            # Register confined project readers before validating subagent role
            # tools. Desktop human mode still needs these handlers for roles,
            # even though its manual model adapter does not bind declarations.
            from vera.desktop.project_tools import register_project_tools

            register_project_tools(registry, Path(workspace).expanduser().resolve())
        agent = get_agent(model, env, config.get("agent", {}), default_type=default_type, tool_registry=registry)
        context_config = config.get("user_context") or {}
        directory = context_config.get("directory") or USER_CONTEXT_DIRECTORY
        apply_user_context(agent, UserContext(directory).render())
        if subagents.roles:
            register_subagent_tools(registry, agent, subagents, model_config, catalog)
        policy = sandbox.model_dump_json() if sandbox else ""
        if permissions.mode != "standard":
            policy = json.dumps({"sandbox": policy, "permissions": permissions.mode}, sort_keys=True)
        if "mcp_selection" in config:
            policy = json.dumps({"sandbox": policy, "mcp_selection": sorted(config["mcp_selection"])}, sort_keys=True)
        if plugins.versions:
            policy = json.dumps({"sandbox": policy, "plugins": plugins.versions}, sort_keys=True)
        if scheduled.enabled and not readonly:
            policy = json.dumps(
                {"runtime": policy, "scheduler": str(scheduled.directory.expanduser().resolve())}, sort_keys=True
            )
        if config.get("run_mode") in {"plan", "goal"}:
            policy = json.dumps({"runtime": policy, "run_mode": config["run_mode"]}, sort_keys=True)
        yield AgentRuntime(agent, catalog, workspace.expanduser(), policy, plugins.versions, mode)
