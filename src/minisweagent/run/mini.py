#!/usr/bin/env python3

"""Run mini-SWE-agent in your local environment. This is the default executable `mini`."""
# Read this first: https://mini-swe-agent.com/latest/usage/mini/  (usage)

import os
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer
from pydantic import ValidationError
from rich.console import Console

from minisweagent import global_config_dir
from minisweagent.agents import get_agent
from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.subagents import SubagentConfig, register_subagent_tools
from minisweagent.agents.utils.prompt_user import _multiline_prompt
from minisweagent.config import builtin_config_dir, get_config_from_spec
from minisweagent.environments import get_environment
from minisweagent.environments.sandbox import SandboxConfig, SandboxMode, open_runtime
from minisweagent.models import get_model
from minisweagent.run.utilities.config import configure_if_first_time
from minisweagent.storage import RunStore, StorageConfig, StorageError
from minisweagent.tools import ToolError, make_tool_registry
from minisweagent.tools.mcp import open_mcp_tools, parse_mcp_servers
from minisweagent.tools.skills import SkillConfig, discover_skills, get_skill, register_skill_tools
from minisweagent.tools.web import WebConfig, configure_web_tools
from minisweagent.utils.serialize import UNSET, recursive_merge

DEFAULT_CONFIG_FILE = Path(os.getenv("MSWEA_MINI_CONFIG_PATH", builtin_config_dir / "mini.yaml"))
DEFAULT_OUTPUT_FILE = global_config_dir / "last_mini_run.traj.json"


_HELP_TEXT = """Run mini-SWE-agent in your local environment.

[not dim]
More information about the usage: [bold green]https://mini-swe-agent.com/latest/usage/mini/[/bold green]
[/not dim]
"""

_CONFIG_SPEC_HELP_TEXT = """Path to config files, filenames, or key-value pairs.

[bold red]IMPORTANT:[/bold red] [red]If you set this option, the default config file will not be used.[/red]
So you need to explicitly set it e.g., with [bold green]-c mini.yaml <other options>[/bold green]

Multiple configs will be recursively merged.

Examples:

[bold red]-c model.model_kwargs.temperature=0[/bold red] [red]You forgot to add the default config file! See above.[/red]

[bold green]-c mini.yaml -c model.model_kwargs.temperature=0.5[/bold green]

[bold green]-c swebench.yaml agent.mode=yolo[/bold green]
"""

console = Console(highlight=False)
app = typer.Typer(rich_markup_mode="rich")


# fmt: off
@app.command(help=_HELP_TEXT)
def main(
    model_name: str | None = typer.Option(None, "-m", "--model", help="Model to use",),
    model_class: str | None = typer.Option(None, "--model-class", help="Model class to use (e.g., 'litellm' or 'minisweagent.models.litellm_model.LitellmModel')", rich_help_panel="Advanced"),
    agent_class: str | None = typer.Option(None, "--agent-class", help="Agent class to use (e.g., 'interactive' or 'minisweagent.agents.interactive.InteractiveAgent')", rich_help_panel="Advanced"),
    environment_class: str | None = typer.Option(None, "--environment-class", help="Environment class to use (e.g., 'local' or 'minisweagent.environments.local.LocalEnvironment')", rich_help_panel="Advanced"),
    sandbox_mode: Annotated[SandboxMode | None, typer.Option("--sandbox", help="Choose workspace isolation or explicit local execution.")] = None,
    task: str | None = typer.Option(None, "-t", "--task", help="Task/problem statement", show_default=False),
    skill: Annotated[str | None, typer.Option("--skill", help="Load a local skill into the initial task.")] = None,
    storage_path: Annotated[Path | None, typer.Option("--storage", help="Record this run in a SQLite database.")] = None,
    resume_from: Annotated[str | None, typer.Option("--resume", help="Continue a stored run from its checkpoint.")] = None,
    reconciliation: Annotated[str | None, typer.Option("--reconcile", help="Verified outcome of unresolved tool calls.")] = None,
    yolo: bool = typer.Option(False, "-y", "--yolo", help="Run without confirmation"),
    cost_limit: float | None = typer.Option(None, "-l", "--cost-limit", help="Cost limit. Set to 0 to disable."),
    config_spec: list[str] = typer.Option([str(DEFAULT_CONFIG_FILE)], "-c", "--config", help=_CONFIG_SPEC_HELP_TEXT),
    output: Path | None = typer.Option(DEFAULT_OUTPUT_FILE, "-o", "--output", help="Output trajectory file"),
    exit_immediately: bool = typer.Option(False, "--exit-immediately", help="Exit immediately when the agent wants to finish instead of prompting.", rich_help_panel="Advanced"),
) -> Any:
    # fmt: on
    configure_if_first_time()

    # Build the config from the command line arguments
    console.print(f"Building agent config from specs: [bold green]{config_spec}[/bold green]")
    configs = [get_config_from_spec(spec) for spec in config_spec]
    configs.append({
        "run": {
            "task": task or UNSET,
        },
        "agent": {
            "agent_class": agent_class or UNSET,
            "mode": "yolo" if yolo else UNSET,
            "cost_limit": cost_limit if cost_limit is not None else UNSET,
            "confirm_exit": False if exit_immediately else UNSET,
            "output_path": output or UNSET,
        },
        "model": {
            "model_class": model_class or UNSET,
            "model_name": model_name or UNSET,
        },
        "environment": {
            "environment_class": environment_class or UNSET,
        },
    })
    if sandbox_mode is not None:
        configs.append({"sandbox": {"mode": sandbox_mode.value}})
    if storage_path is not None:
        configs.append({"storage": {"path": storage_path}})
    config = recursive_merge(*configs)

    if reconciliation is not None and (resume_from is None or not reconciliation.strip()):
        raise typer.BadParameter("Supply a nonempty reconciliation with --resume.")
    run_task = config.get("run", {}).get("task", UNSET)
    if resume_from:
        if task or skill:
            raise typer.BadParameter("--resume uses the original task and selected skill.")
        run_task = ""
    elif run_task is UNSET:
        console.print("[bold yellow]What do you want to do?")
        run_task = _multiline_prompt()
        console.print("[bold green]Got that, thanks![/bold green]")

    model_config = config.get("model", {})
    model = get_model(config=model_config)
    web = WebConfig.model_validate(config.get("web", {}))
    try:
        skill_config = SkillConfig.model_validate(config.get("skills", {}))
        subagents = SubagentConfig.model_validate(config.get("subagents", {}))
        sandbox = SandboxConfig.model_validate(config["sandbox"]) if "sandbox" in config else None
        storage = StorageConfig.model_validate(config.get("storage", {})) if "storage" in config or resume_from else None
    except ValidationError as error:
        issue = error.errors(include_input=False)[0]
        field = ".".join(map(str, issue["loc"])) or "config"
        raise typer.BadParameter(f"{field}: {issue['msg']}") from None
    with ExitStack() as stack:
        agent_options = {}
        agent_config = config.get("agent", {})
        run_id = uuid4().hex if storage else None
        if run_id and agent_config.get("output_path") == DEFAULT_OUTPUT_FILE:
            agent_config = agent_config | {"output_path": DEFAULT_OUTPUT_FILE.parent / "runs" / f"{run_id}.traj.json"}
        try:
            servers = parse_mcp_servers(config.get("mcp_servers", {}))
            has_web_tools = bool(web.search_provider or web.extract_provider)
            environment_config = config.get("environment", {})
            if sandbox is None:
                env = get_environment(environment_config, default_type="local")
            else:
                sandbox.check_external_tools(
                    web_enabled=has_web_tools,
                    stdio={name for name, server in servers.items() if server.command},
                    http={name for name, server in servers.items() if server.url},
                )
                env, mode = stack.enter_context(open_runtime(sandbox, environment_config))
                console.print(f"Execution mode: {mode}")
            catalog = discover_skills(skill_config, Path.cwd())
            if skill is not None:
                selected = get_skill(catalog, skill).view()
                run_task = (
                    f"{run_task}\n\nUse the explicitly selected skill {skill!r}. Its directory is {selected['directory']}.\n\n"
                    f"{selected['content']}"
                )
            has_skill_tools = bool(catalog) and callable(getattr(model, "bind_tool_registry", None)) and getattr(
                model, "supports_tool_registry", True
            )
            if has_web_tools or servers or has_skill_tools or subagents.roles:
                registry = make_tool_registry(env)
                configure_web_tools(registry, web)
                stack.enter_context(open_mcp_tools(registry, servers))
                if has_skill_tools:
                    register_skill_tools(registry, catalog)
                agent_options["tool_registry"] = registry
            agent = get_agent(model, env, agent_config, default_type="interactive", **agent_options)
            if subagents.roles:
                register_subagent_tools(registry, agent, subagents, model_config, catalog)
        except ToolError as error:
            raise typer.BadParameter(str(error)) from None
        try:
            if storage is not None:
                if not isinstance(agent, DefaultAgent):
                    raise StorageError("Run storage requires a DefaultAgent-compatible agent.")
                workspace = sandbox.workspace if sandbox is not None else Path(getattr(env.config, "cwd", "") or ".")
                with RunStore(storage.path).track(
                    agent, run_id=run_id, resume_from=resume_from, reconciliation=reconciliation,
                    workspace=workspace.expanduser(),
                    runtime_policy=sandbox.model_dump_json() if sandbox is not None else "",
                ) as record:
                    console.print(f"Run ID: {record.id}")
                    agent.run(record.resume.task if record.resume else run_task)
            else:
                agent.run(run_task)
        except StorageError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(1) from None
    if (output_path := agent_config.get("output_path")):
        console.print(f"Saved trajectory to [bold green]'{output_path}'[/bold green]")
    return agent


if __name__ == "__main__":
    app()
