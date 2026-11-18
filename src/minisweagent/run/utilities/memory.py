"""Inspect and retain notes in the configured Hindsight memory bank."""

import json
from typing import Annotated

import typer

from minisweagent.memory.hindsight import HindsightError, HindsightMemory

app = typer.Typer(no_args_is_help=True)


@app.command()
def retain(
    note: str,
    context: str = "",
    document_id: str = "",
    tag: Annotated[list[str] | None, typer.Option()] = None,
) -> None:
    """Save an explicit project note to Hindsight."""
    try:
        memory = HindsightMemory.from_env()
        memory.retain(note, context=context, document_id=document_id, tags=tuple(tag or ()))
    except HindsightError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Saved note to Hindsight bank {memory.bank_id}.")


@app.command()
def recall(query: str, facts_only: bool = False, json_output: bool = False) -> None:
    """Show the notes Hindsight recalls for a query."""
    try:
        records = HindsightMemory.from_env().recall_records(query, prefer_observations=not facts_only)
    except HindsightError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    if json_output:
        typer.echo(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        typer.echo("\n\n".join(record["text"] for record in records) if records else "No project memories found.")


@app.command()
def reflect(query: str, json_output: bool = False) -> None:
    """Synthesize an answer using Hindsight's observations and mental models."""
    try:
        result = HindsightMemory.from_env().reflect(query)
    except HindsightError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2) if json_output else result["text"])


@app.command()
def invalidate(memory_id: str, reason: str) -> None:
    """Retire a specific stale fact by ID and record a reason."""
    _set_validity(memory_id, is_valid=False, reason=reason)


@app.command()
def restore(memory_id: str) -> None:
    """Restore an invalidated fact by ID."""
    _set_validity(memory_id, is_valid=True)


def _set_validity(memory_id: str, *, is_valid: bool, reason: str = "") -> None:
    try:
        HindsightMemory.from_env().set_validity(memory_id, is_valid=is_valid, reason=reason)
    except HindsightError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{'Restored' if is_valid else 'Invalidated'} fact {memory_id}.")
