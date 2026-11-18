#!/usr/bin/env python3

"""Run mini-SWE-agent in your local environment. This is the default executable `mini`."""
# Read this first: https://mini-swe-agent.com/latest/usage/mini/  (usage)

import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer
from pydantic import ValidationError
from rich.console import Console

from minisweagent import global_config_dir
from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.utils.prompt_user import _multiline_prompt
from minisweagent.config import builtin_config_dir, get_config_from_spec
from minisweagent.environments.sandbox import SandboxMode
from minisweagent.environments.sandbox_profiles import resolve_sandbox_profile
from minisweagent.plugins import PluginError
from minisweagent.run.utilities.config import configure_if_first_time
from minisweagent.runtime import open_agent_runtime
from minisweagent.storage import RunStore, StorageConfig, StorageError
from minisweagent.terminal.files import MENTION, ProjectFiles
from minisweagent.terminal.session import TerminalSession
from minisweagent.terminal.ui import bind_session, completion_context, read_task
from minisweagent.tools import ToolError
from minisweagent.tools.skills import get_skill
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
    sandbox_profile: Annotated[str | None, typer.Option("--sandbox-profile", help="Use a saved sandbox profile.")] = None,
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
    if sandbox_profile is not None:
        config["sandbox_profile"] = sandbox_profile
    if sandbox_mode is not None and config.get("sandbox_profile"):
        raise typer.BadParameter("Choose either --sandbox or --sandbox-profile, not both.")
    if config.get("sandbox_profile"):
        workspace = config.get("sandbox", {}).get("workspace") or config.get("environment", {}).get("cwd") or Path.cwd()
        try:
            config = resolve_sandbox_profile(config, Path(workspace))
        except (ToolError, ValidationError) as error:
            raise typer.BadParameter(str(error)) from None

    if reconciliation is not None and (resume_from is None or not reconciliation.strip()):
        raise typer.BadParameter("Supply a nonempty reconciliation with --resume.")
    run_task = config.get("run", {}).get("task", UNSET)
    session = None
    if resume_from:
        if task or skill:
            raise typer.BadParameter("--resume uses the original task and selected skill.")
        run_task = ""
    elif run_task is UNSET:
        workspace = config.get("sandbox", {}).get("workspace") or config.get("environment", {}).get("cwd") or Path.cwd()
        session = TerminalSession(config, Path(workspace))
        console.print("[bold yellow]What do you want to do?")
        console.print("/help: commands; @ + Tab: project files; Esc Enter: submit.", markup=False)
        with completion_context(session):
            run_task = read_task(session, _multiline_prompt, _show_session_message)
        if run_task is None:
            return None
        console.print("[bold green]Got that, thanks![/bold green]")
    elif not resume_from and isinstance(run_task, str) and MENTION.search(run_task):
        workspace = config.get("sandbox", {}).get("workspace") or config.get("environment", {}).get("cwd") or Path.cwd()
        try:
            run_task = ProjectFiles(Path(workspace)).attach(run_task)
        except ToolError as error:
            raise typer.BadParameter(str(error)) from None

    while True:
        current = session.runtime_config() if session else config
        with completion_context(session) if session else nullcontext():
            agent = _run_task(current, run_task, skill, resume_from, reconciliation, session)
            if session is None or exit_immediately or not (sys.stdin and sys.stdin.isatty()):
                return agent
            console.print("[bold yellow]Next task (/new, /help, @file; Ctrl+D to exit):[/bold yellow]")
            run_task = read_task(session, _multiline_prompt, _show_session_message)
            if run_task is None:
                return agent
            # Keep previous task artifacts when the same session starts another run.
            path = current.get("agent", {}).get("output_path")
            if path:
                path = Path(path)
                session.config.setdefault("agent", {})["output_path"] = path.parent / f"{path.stem.split('.session-')[0]}.session-{uuid4().hex[:8]}{path.suffix}"


def _show_session_message(message: str) -> None:
    console.print(message, markup=False)


def _run_task(config, run_task, skill, resume_from, reconciliation, session=None):
    """Assemble and close one task's resources; terminal session choices stay outside the agent loop."""
    agent_config = config.get("agent", {})
    run_id = uuid4().hex if "storage" in config or resume_from else None
    if run_id and agent_config.get("output_path") == DEFAULT_OUTPUT_FILE:
        agent_config = agent_config | {"output_path": DEFAULT_OUTPUT_FILE.parent / "runs" / f"{run_id}.traj.json"}
        config["agent"] = agent_config
    try:
        storage = StorageConfig.model_validate(config.get("storage", {})) if run_id else None
        with open_agent_runtime(config) as runtime:
            agent = runtime.agent
            if session is not None:
                bind_session(agent, session, _show_session_message)
            if runtime.mode is not None:
                console.print(f"Execution mode: {runtime.mode}")
            if skill is not None:
                selected = get_skill(runtime.skills, skill).view()
                run_task = (
                    f"{run_task}\n\nUse the explicitly selected skill {skill!r}. Its directory is {selected['directory']}.\n\n"
                    f"{selected['content']}"
                )
            if storage is not None:
                if not isinstance(agent, DefaultAgent):
                    raise StorageError("Run storage requires a DefaultAgent-compatible agent.")
                with RunStore(storage.path).track(
                    agent, run_id=run_id, resume_from=resume_from, reconciliation=reconciliation,
                    workspace=runtime.workspace, runtime_policy=runtime.policy,
                ) as record:
                    console.print(f"Run ID: {record.id}")
                    agent.run(record.resume.task if record.resume else run_task)
            else:
                agent.run(run_task)
            if runtime.plugin_versions and agent_config.get("output_path"):
                agent.save(Path(agent_config["output_path"]), {"info": {"plugins": runtime.plugin_versions}})
    except (ToolError, PluginError) as error:
        raise typer.BadParameter(str(error)) from None
    except ValidationError as error:
        issue = error.errors(include_input=False)[0]
        field = ".".join(map(str, issue["loc"])) or "config"
        raise typer.BadParameter(f"{field}: {issue['msg']}") from None
    except StorageError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    if (output_path := agent_config.get("output_path")):
        console.print(f"Saved trajectory to [bold green]'{output_path}'[/bold green]")
    return agent


if __name__ == "__main__":
    app()
