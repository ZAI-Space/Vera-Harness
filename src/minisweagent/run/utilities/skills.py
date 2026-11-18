"""Inspect the local skill catalog without starting an agent or a model."""

from pathlib import Path

import typer

from minisweagent.tools import ToolError
from minisweagent.tools.skills import Skill, SkillConfig, discover_skills, get_skill

app = typer.Typer(help="List and inspect Agent Skills from the project and user skill directories.")


def _catalog(directories: list[Path] | None) -> dict[str, Skill]:
    try:
        return discover_skills(SkillConfig(directories=directories or []), Path.cwd())
    except ToolError as error:
        raise typer.BadParameter(str(error)) from None


@app.command("list")
def list_skills(directory: list[Path] | None = typer.Option(None, "--directory", "-d")) -> None:
    """Print one name and description per skill. Pass -d to add an external root."""
    for skill in _catalog(directory).values():
        typer.echo(f"{skill.name}\t{skill.description}".encode())


@app.command()
def show(
    name: str,
    file_path: str | None = typer.Argument(None),
    directory: list[Path] | None = typer.Option(None, "--directory", "-d"),
) -> None:
    """Print the skill instructions or a supporting file by its relative path."""
    try:
        result = get_skill(_catalog(directory), name).view(file_path)
    except ToolError as error:
        raise typer.BadParameter(str(error)) from None
    # Keep redirected output in UTF-8 even under legacy Windows code pages.
    typer.echo(result["content"].encode())
