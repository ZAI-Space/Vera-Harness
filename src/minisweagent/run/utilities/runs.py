"""Inspect run records and request cancellation from the CLI."""

import json
from pathlib import Path
from typing import Annotated

import typer

from minisweagent.storage import DEFAULT_STORAGE_PATH, RunStore, StorageError

app = typer.Typer(help="Inspect local SQLite run records and request cancellation.")
DatabasePath = Annotated[Path, typer.Option("--db", help="Path to the run database.")]


@app.command("list")
def list_runs(
    db: DatabasePath = DEFAULT_STORAGE_PATH,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 20,
) -> None:
    """List the newest runs first."""
    try:
        runs = RunStore(db).list_runs(limit)
    except StorageError as error:
        raise typer.BadParameter(str(error), param_hint="--db") from None
    typer.echo(json.dumps(runs, indent=2))


@app.command("show")
def show(run_id: str, db: DatabasePath = DEFAULT_STORAGE_PATH) -> None:
    """Show a run, its direct children and its tool receipts."""
    try:
        run = RunStore(db).get_run(run_id)
    except StorageError as error:
        raise typer.BadParameter(str(error), param_hint="--db") from None
    if run is None:
        raise typer.BadParameter(f"No run with ID {run_id!r}.", param_hint="run_id")
    typer.echo(json.dumps(run, indent=2))


@app.command()
def cancel(run_id: str, db: DatabasePath = DEFAULT_STORAGE_PATH) -> None:
    """Request cancellation at the next runtime boundary."""
    try:
        RunStore(db).request_cancel(run_id)
    except StorageError as error:
        raise typer.BadParameter(str(error), param_hint="run_id") from None
    typer.echo(f"Cancellation requested for {run_id}.")
