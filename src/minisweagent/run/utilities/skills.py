"""Inspect local skills or explicitly search and install market snapshots without starting a model."""

import json
from pathlib import Path

import typer

from minisweagent.markets.skills import SkillMarket, remove_market_skill
from minisweagent.tools import ToolError
from minisweagent.tools.skills import Skill, SkillConfig, discover_skills, get_skill

app = typer.Typer(help="List and inspect Agent Skills from the project and user skill directories.")


def _market(operation):
    try:
        typer.echo(json.dumps(operation(), ensure_ascii=True, indent=2))
    except (ToolError, OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None


@app.command()
def search(query: str, limit: int = 20):
    """Search the preconfigured skills.sh market without installing or executing anything."""
    _market(lambda: SkillMarket().search(query, limit))


@app.command()
def inspect(identifier: str, ref: str = "HEAD"):
    """Preview instructions, assets and a pinned commit without installing the skill."""
    _market(lambda: SkillMarket().inspect(identifier, ref=ref))


@app.command()
def install(identifier: str, directory: Path | None = None, ref: str = "HEAD"):
    """Install one owner/repo/skill snapshot; its resolved commit is recorded."""
    _market(lambda: SkillMarket().install(identifier, directory=directory, ref=ref))


@app.command()
def remove(name: str, directory: Path | None = None):
    """Remove an unmodified market-owned skill; local changes are preserved."""
    _market(lambda: remove_market_skill(name, directory))


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
