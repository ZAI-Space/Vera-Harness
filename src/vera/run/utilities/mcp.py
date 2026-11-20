"""Find, inspect and add MCP services from the preconfigured official Registry."""

import json
from pathlib import Path

import typer

from vera.markets.mcp import DEFAULT_DIRECTORY, MCPRegistry, MCPServices
from vera.tools import ToolError

app = typer.Typer(help=__doc__, no_args_is_help=True)


def _run(operation):
    try:
        result = operation()
    except (ToolError, OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from None
    if result is not None:
        typer.echo(json.dumps(result, ensure_ascii=True, indent=2))


@app.command()
def search(query: str = "", cursor: str = "", limit: int = 20):
    """Search latest active publisher records, with a pagination cursor."""
    _run(lambda: MCPRegistry().search(query, cursor=cursor, limit=limit))


@app.command()
def inspect(identifier: str, name: str | None = None, version: str = "latest"):
    """Preview a pinned transport, required inputs and prerequisite tools."""
    _run(lambda: MCPRegistry().preview(identifier, name=name, version=version))


@app.command()
def add(
    identifier: str,
    name: str | None = None,
    version: str = "latest",
    directory: Path = DEFAULT_DIRECTORY,
    input_value: list[str] = typer.Option(None, "--input"),
    header_env: list[str] = typer.Option(None, "--header-env"),
):
    """Save a service without activating it; inputs use NAME=VALUE, header credentials use HEADER=ENV_NAME."""

    def install():
        def pairs(values):
            result = {}
            for value in values or []:
                key, separator, content = value.partition("=")
                if not key or not separator or not content:
                    raise ToolError("Use NAME=VALUE or HEADER=ENV_NAME.")
                result[key] = content
            return result

        return MCPServices(directory).add(
            MCPRegistry().preview(
                identifier, name=name, version=version, inputs=pairs(input_value), header_env=pairs(header_env)
            )
        )

    _run(install)


@app.command("list")
def list_services(directory: Path = DEFAULT_DIRECTORY):
    """List added services; they require an explicit /mcp selection to run."""
    _run(MCPServices(directory).list)


@app.command()
def remove(name: str, directory: Path = DEFAULT_DIRECTORY):
    """Delete saved settings without stopping another session's connection."""
    _run(lambda: MCPServices(directory).remove(name))


if __name__ == "__main__":
    app()
