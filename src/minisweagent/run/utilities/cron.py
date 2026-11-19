"""Manage persistent scheduled agent jobs and their independent background service."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from minisweagent.scheduler.config import DEFAULT_DIRECTORY
from minisweagent.scheduler.engine import Scheduler, service_status, start_service, stop_service
from minisweagent.scheduler.store import JobStore
from minisweagent.tools import ToolError

app = typer.Typer(help="Schedule independent Vera tasks; requires a running scheduler service.", no_args_is_help=True)


@app.callback()
def configure(context: typer.Context, state: Annotated[Path, typer.Option("--state")] = DEFAULT_DIRECTORY):
    """Choose the private job store shared by settings, tools and the daemon."""
    context.obj = JobStore(state)


def _run(operation: Callable):
    try:
        result = operation()
    except ValidationError as error:
        issue = error.errors(include_input=False)[0]
        raise typer.BadParameter(f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}") from None
    except (ToolError, OSError, yaml.YAMLError) as error:
        raise typer.BadParameter(str(error)) from None
    if result is not None:
        typer.echo(json.dumps(result, ensure_ascii=True, indent=2))


@app.command("create")
def create(context: typer.Context, definition: Path):
    """Save a JobSpec YAML/JSON definition; no agent or provider call is made."""
    _run(lambda: context.obj.create(yaml.safe_load(definition.read_text(encoding="utf-8-sig"))))


@app.command("list")
def list_jobs(context: typer.Context):
    """List schedules without exposing stored provider credentials."""
    _run(context.obj.list)


@app.command()
def show(context: typer.Context, job: str):
    """Show safe job metadata and recent execution history."""
    _run(lambda: context.obj.get(job) | {"executions": context.obj.history(job)})


@app.command()
def update(context: typer.Context, job: str, definition: Path, revision: int | None = None):
    """Replace a definition, optionally requiring the displayed revision to match."""
    _run(lambda: context.obj.update(job, yaml.safe_load(definition.read_text(encoding="utf-8-sig")), revision=revision))


@app.command()
def pause(context: typer.Context, job: str):
    """Pause future starts; ongoing calls can be cancelled by execution ID."""
    _run(lambda: context.obj.control(job, "pause"))


@app.command()
def resume(context: typer.Context, job: str):
    """Resume a paused schedule, applying its missed-run policy."""
    _run(lambda: context.obj.control(job, "resume"))


@app.command()
def remove(context: typer.Context, job: str):
    """Remove the schedule while retaining its execution history."""
    _run(lambda: context.obj.control(job, "remove"))


@app.command("run")
def run_now(context: typer.Context, job: str):
    """Queue a manual occurrence without consuming the next regular slot."""
    _run(lambda: context.obj.control(job, "run"))


@app.command()
def history(context: typer.Context, job: str | None = None, limit: int = 50):
    """List outcomes, summaries and RunStore trace IDs."""
    _run(lambda: context.obj.history(job, limit))


@app.command()
def cancel(context: typer.Context, execution: str):
    """Cancel a queued or running invocation, without cancelling future scheduled slots."""
    _run(lambda: context.obj.cancel(execution))


@app.command()
def tick(context: typer.Context, workers: int = 2):
    """Dispatch currently due work once and wait for completion; no persistent service is installed."""

    def dispatch():
        with Scheduler(context.obj.directory, workers=workers).owned() as scheduler:
            keys = scheduler.tick()
            scheduler.wait()
            return {"executions": keys}

    _run(dispatch)


@app.command()
def serve(context: typer.Context, workers: int = 2, interval: float = 1):
    """Run in the foreground until cron stop or Ctrl+C."""
    _run(lambda: Scheduler(context.obj.directory, workers=workers).serve(interval=interval))


@app.command()
def start(context: typer.Context, workers: int = 2):
    """Start a detached service that survives closing the CLI/desktop application."""
    _run(lambda: start_service(context.obj.directory, workers=workers))


@app.command()
def stop(context: typer.Context):
    """Request orderly service shutdown and cancellation of its active workers."""
    _run(lambda: stop_service(context.obj.directory))


@app.command()
def status(context: typer.Context):
    """Report whether the scheduler process is actually alive."""
    _run(lambda: service_status(context.obj.directory))


if __name__ == "__main__":
    app()
