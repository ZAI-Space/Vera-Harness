"""Configure named sandboxes independently of model credentials and the terminal UI."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError

from minisweagent.environments.sandbox_profiles import SandboxProfiles, SandboxProfileSettings
from minisweagent.tools import ToolError

app = typer.Typer(
    help="Manage user-configured Docker/Bubblewrap environments; never install engines or images.", no_args_is_help=True
)


@app.callback()
def configure(context: typer.Context, store: Annotated[Path, typer.Option("--store")] = SandboxProfileSettings().path):
    """Select the user store also exposed through sandbox_profiles.path in runtime config."""
    context.obj = SandboxProfiles(store)


def _run(operation: Callable):
    try:
        value = operation()
    except ValidationError as error:
        issue = error.errors(include_input=False)[0]
        raise typer.BadParameter(f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}") from None
    except (ToolError, OSError, yaml.YAMLError) as error:
        raise typer.BadParameter(str(error)) from None
    if value is not None:
        typer.echo(json.dumps(value, ensure_ascii=True, indent=2))


@app.command("list")
def list_profiles(context: typer.Context):
    """List saved configuration; perform no runtime probes or downloads."""
    _run(lambda: {name: profile.model_dump(mode="json") for name, profile in context.obj.list_profiles().items()})


@app.command()
def save(context: typer.Context, name: str, config: Path, replace: bool = False):
    """Save a SandboxConfig YAML/JSON file; --replace explicitly updates an existing name."""
    _run(lambda: context.obj.save(name, yaml.safe_load(config.read_text(encoding="utf-8-sig")), replace=replace))


@app.command()
def remove(context: typer.Context, name: str):
    """Remove a profile without modifying engines, images, containers or running tasks."""
    _run(lambda: context.obj.remove(name))


@app.command()
def check(context: typer.Context, workspace: Annotated[Path | None, typer.Option("--workspace")] = None):
    """Return picker status and per-profile availability/reasons for the optional current project."""
    _run(lambda: context.obj.status(workspace))


if __name__ == "__main__":
    app()
