#!/usr/bin/env python3

"""Run VERA in your local environment through vera or its compatible mini entry."""

import os
import sys
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer
from pydantic import ValidationError
from rich.console import Console

from vera import global_config_dir
from vera.agents.default import DefaultAgent
from vera.agents.utils.prompt_user import _multiline_prompt
from vera.config import builtin_config_dir, get_config_from_spec
from vera.environments.sandbox import SandboxMode
from vera.environments.sandbox_profiles import resolve_sandbox_profile
from vera.modes.goals import GoalConversationModel, drive_goal
from vera.plugins import PluginError
from vera.run.utilities.config import configure_if_first_time
from vera.runtime import open_agent_runtime
from vera.storage import RunStore, StorageConfig, StorageError
from vera.terminal.files import MENTION, ProjectFiles
from vera.terminal.session import TerminalSession
from vera.terminal.ui import bind_session, completion_context, read_task
from vera.tools import ToolError
from vera.tools.skills import get_skill
from vera.utils.serialize import UNSET, recursive_merge

DEFAULT_CONFIG_FILE = Path(os.getenv("VERA_CONFIG_PATH", builtin_config_dir / "vera.yaml"))
DEFAULT_OUTPUT_FILE = global_config_dir / "last_vera_run.traj.json"


_HELP_TEXT = """Run VERA in your local environment.

[not dim]
Documentation: [bold green]https://github.com/ZAI-Space/Vera-Harness/tree/main/docs[/bold green]
[/not dim]
"""

_CONFIG_SPEC_HELP_TEXT = """Path to config files, filenames, or key-value pairs.

[bold red]IMPORTANT:[/bold red] [red]If you set this option, the default config file will not be used.[/red]
So you need to explicitly set it e.g., with [bold green]-c vera.yaml <other options>[/bold green]

Multiple configs will be recursively merged.

Examples:

[bold red]-c model.model_kwargs.temperature=0[/bold red] [red]You forgot to add the default config file! See above.[/red]

[bold green]-c vera.yaml -c model.model_kwargs.temperature=0.5[/bold green]

[bold green]-c swebench.yaml agent.mode=yolo[/bold green]
"""

console = Console(highlight=False)
app = typer.Typer(rich_markup_mode="rich")


# fmt: off
@app.command(help=_HELP_TEXT)
def main(
    model_name: str | None = typer.Option(None, "-m", "--model", help="Model to use",),
    model_class: str | None = typer.Option(None, "--model-class", help="Model class to use (e.g., 'litellm' or 'vera.models.litellm_model.LitellmModel')", rich_help_panel="Advanced"),
    agent_class: str | None = typer.Option(None, "--agent-class", help="Agent class to use (e.g., 'interactive' or 'vera.agents.interactive.InteractiveAgent')", rich_help_panel="Advanced"),
    environment_class: str | None = typer.Option(None, "--environment-class", help="Environment class to use (e.g., 'local' or 'vera.environments.local.LocalEnvironment')", rich_help_panel="Advanced"),
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

    if session is None and not resume_from and isinstance(run_task, str) and run_task.split(maxsplit=1)[:1] in (["/plan"], ["/goal"]):
        workspace = config.get("sandbox", {}).get("workspace") or config.get("environment", {}).get("cwd") or Path.cwd()
        session = TerminalSession(config, Path(workspace))
        result = session.process(run_task)
        if result.kind != "task":
            _show_session_message(result.message)
            return None
        run_task = result.task

    while True:
        current = session.runtime_config() if session else config
        with completion_context(session) if session else nullcontext():
            if session is not None and session.run_mode == "goal":
                def run_goal_turn(prompt, history, remaining):
                    selected = deepcopy(session.runtime_config())
                    options = selected.setdefault("agent", {})
                    if remaining["cost"] > 0:
                        options["cost_limit"] = min(options.get("cost_limit") or remaining["cost"], remaining["cost"])
                    if remaining["seconds"] > 0:
                        options["wall_time_limit_seconds"] = max(1, int(min(options.get("wall_time_limit_seconds") or remaining["seconds"], remaining["seconds"])))
                    options["confirm_exit"] = False
                    if options.get("output_path"):
                        path = Path(options["output_path"])
                        options["output_path"] = path.with_name(f"{path.stem}.goal-{uuid4().hex[:8]}{path.suffix}")
                    return _run_task(selected, session.prepare_task(prompt), skill, None, None, session, history)
                try:
                    agent = drive_goal(session, run_goal_turn, _show_session_message)
                except ToolError as error:
                    raise typer.BadParameter(str(error)) from None
            else:
                agent = _run_task(current, run_task, skill, resume_from, reconciliation, session)
            if session is not None and session.run_mode in {"plan", "goal"} and agent is not None and agent.messages:
                pending_task = agent.messages[-1].get("extra", {}).get("pending_task")
                if pending_task:
                    run_task = pending_task
                    continue
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


def _run_task(config, run_task, skill, resume_from, reconciliation, session=None, goal_history=None):
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
            if goal_history is not None:
                agent.model = GoalConversationModel(agent.model, goal_history)
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
