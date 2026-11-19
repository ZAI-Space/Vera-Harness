"""Operate independent source-evolution experiments without publishing versions."""

import json
from pathlib import Path

import typer
import yaml

from vera.evolution.config import EvolutionConfig, EvolutionError
from vera.evolution.engine import Experiment
from vera.evolution.image import prepare_image
from vera.evolution.repository import source_patch

app = typer.Typer(help="Versioned Vera self-improvement experiments.")


def _print(value: dict) -> None:
    typer.echo(json.dumps(value, ensure_ascii=True, indent=2))


@app.command("prepare-runtime")
def prepare_runtime(source: Path = Path("."), image: str = "vera-evolution-runtime:local"):
    """Build an optional Docker runtime; installs Python dependencies, no model calls."""
    _print({"image": image, "id": prepare_image(source, image)})


@app.command("init")
def initialize(
    root: Path, config: Path = typer.Option(..., "--config", "-c"), source: Path = typer.Option(Path("."), "--source")
):
    """Freeze a committed baseline and an external evaluation manifest; no model calls."""
    try:
        experiment = Experiment.create(
            root, source, EvolutionConfig.model_validate(yaml.safe_load(config.read_text(encoding="utf-8")))
        )
    except EvolutionError as error:
        raise typer.BadParameter(str(error)) from error
    _print({"root": str(experiment.root), "baseline": experiment.state["baseline"]})


@app.command()
def run(root: Path, iterations: int | None = typer.Option(None, min=1), resume: bool = False):
    """Evaluate, rewrite, gate and select generations; use --resume after cancellation."""
    try:
        state = Experiment(root).run(iterations=iterations, resume=resume)
    except EvolutionError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    _print(
        {
            "status": state["status"],
            "best": state["best"],
            "spent": state["spent"],
            "generations": len(state["versions"]) - 1,
        }
    )


@app.command()
def status(root: Path):
    """Read immutable version references, decisions, costs and artifact paths."""
    _print(Experiment(root).state)


@app.command()
def baseline(root: Path):
    """Run checks and baseline tasks without generating a candidate (may incur costs)."""
    try:
        state = Experiment(root).run(iterations=0)
    except EvolutionError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    _print(state["versions"][0])


@app.command()
def cancel(root: Path):
    """Request termination of the active subprocess tree; this does not need its lock."""
    experiment = Experiment(root)
    experiment.cancel_path.touch()
    _print({"cancel_requested": True})


@app.command()
def rollback(root: Path, version: str):
    """Select a previously accepted generation for future runs; retain all history."""
    try:
        Experiment(root).rollback(version)
    except EvolutionError as error:
        raise typer.BadParameter(str(error)) from error
    _print({"best": Experiment(root).state["best"]})


@app.command()
def holdout(root: Path, version: str = "best"):
    """Run final holdout separately; results never drive automatic version selection."""
    try:
        _print(Experiment(root).holdout(version))
    except EvolutionError as error:
        raise typer.BadParameter(str(error)) from error


@app.command("export")
def export_patch(root: Path, output: Path, version: str = "best"):
    """Export the selected source diff for review on a normal Gitflow task branch."""
    experiment = Experiment(root)
    selected = experiment.version(version)
    if selected["status"] not in {"baseline", "accepted"}:
        raise typer.BadParameter("Export a baseline or accepted generation.")
    patch = source_patch(experiment.root / "archive", experiment.state["baseline"], selected["sha"])
    with output.open("xb") as stream:
        stream.write(patch)
    _print({"patch": str(output.resolve()), "baseline": experiment.state["baseline"], "candidate": selected["sha"]})


if __name__ == "__main__":
    app()
