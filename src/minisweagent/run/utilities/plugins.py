"""Inspect GitHub markets and explicitly manage downloadable Vera capability packages."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from minisweagent import global_config_dir
from minisweagent.plugins import PluginError, PluginManager
from minisweagent.plugins.source import PluginSource

app = typer.Typer(help="Manage plugins independently of the agent and model.", no_args_is_help=True)
marketplace_app = typer.Typer(help="Choose GitHub or Gitee plugin marketplaces.", no_args_is_help=True)
app.add_typer(marketplace_app, name="marketplace")


@app.callback()
def configure(
    context: typer.Context,
    directory: Annotated[Path, typer.Option("--directory", help="User-owned plugin store.")] = global_config_dir
    / "plugins",
) -> None:
    """Choose the same store used by plugins.directory in agent config."""
    context.obj = PluginManager(directory)


def _run(operation: Callable):
    try:
        value = operation()
    except (PluginError, OSError) as error:
        raise typer.BadParameter(str(error)) from None
    if value is not None:
        typer.echo(json.dumps(value, ensure_ascii=True, indent=2))


@app.command("list")
def list_plugins(context: typer.Context):
    """List installed versions and activation state without fetching or starting a model."""
    _run(context.obj.list_plugins)


@app.command()
def install(
    context: typer.Context,
    source: str,
    ref: str = "HEAD",
    path: str = ".",
    enable: bool = False,
    host: PluginSource = typer.Option(PluginSource.github, "--source"),
):
    """Install owner/repo, a local directory or NAME@MARKETPLACE; --enable approves its code."""

    def operation():
        if "@" in source and not Path(source).exists():
            if ref != "HEAD" or path != ".":
                raise PluginError("Catalog installs use their saved path/ref; refresh the marketplace first.")
            name, market = source.split("@", 1)
            result = context.obj.install_from_marketplace(name, market)
        elif "/" not in source and "\\" not in source and not Path(source).exists():
            if ref != "HEAD" or path != ".":
                raise PluginError("Named installs use the selected catalog's revision and path.")
            result = context.obj.install_named(source)
        else:
            result = context.obj.install(source, ref, path, host=host)
        if enable:
            context.obj.set_enabled(result["name"], True)
            result["enabled"] = True
        return result

    _run(operation)


@app.command()
def show(context: typer.Context, name: str):
    """Inspect commands, endpoints, capability names, source commit and version history."""
    _run(lambda: context.obj.show(name))


@app.command()
def enable(context: typer.Context, name: str):
    """Approve the installed current digest for future runs, including its MCP commands."""
    _run(lambda: context.obj.set_enabled(name, True))


@app.command()
def disable(context: typer.Context, name: str):
    """Stop loading a plugin in new runs without deleting its versions."""
    _run(lambda: context.obj.set_enabled(name, False))


@app.command()
def update(context: typer.Context, name: str, ref: str | None = None):
    """Download the saved source/catalog revision; changed packages require enable again."""
    _run(lambda: context.obj.update(name, ref))


@app.command()
def rollback(context: typer.Context, name: str, digest: str):
    """Select a full historical digest from show; enable it explicitly after review."""
    _run(lambda: context.obj.rollback(name, digest))


@app.command()
def uninstall(context: typer.Context, name: str):
    """Remove registration/history; cached files remain available to already running sessions."""
    _run(lambda: context.obj.uninstall(name))


@marketplace_app.command("use")
def use_marketplace(context: typer.Context, source: PluginSource):
    """Choose github or gitee; fetch the built-in catalog without installing plugins."""
    _run(lambda: context.obj.use_marketplace(source))


@marketplace_app.command("list")
def list_marketplaces(context: typer.Context):
    """List saved market names, source commits and installable/unsupported catalog entries."""
    _run(
        lambda: {
            "selected": context.obj.selected_marketplace(),
            "marketplaces": {
                name: {
                    "source": market["source"],
                    "ref": market["ref"],
                    "commit": market["commit"],
                    "plugins": len(market["plugins"]),
                }
                for name, market in context.obj.list_marketplaces().items()
            },
        }
    )


@marketplace_app.command("search")
def search(context: typer.Context, query: Annotated[str, typer.Argument()] = "", marketplace: str | None = None):
    """Search saved catalog names without network access."""

    def operation():
        markets = context.obj.list_marketplaces()
        selected = marketplace or context.obj.selected_marketplace()
        if marketplace is not None and marketplace not in markets:
            raise PluginError(f"Unknown marketplace {marketplace!r}.")
        return {
            f"{name}@{market}": {
                "installable": not bool(entry.get("unsupported")),
                **({"reason": entry["unsupported"]} if entry.get("unsupported") else {}),
            }
            for market, catalog in markets.items()
            if selected is None or selected == market
            for name, entry in catalog["plugins"].items()
            if query.lower() in name.lower()
        }

    _run(operation)


@marketplace_app.command("refresh")
def refresh(context: typer.Context, name: str):
    """Refresh one market atomically; installed packages are updated separately."""
    _run(lambda: context.obj.refresh_marketplace(name))


@marketplace_app.command("remove")
def remove_marketplace(context: typer.Context, name: str):
    """Remove a market without uninstalling its explicitly installed packages."""
    _run(lambda: context.obj.remove_marketplace(name))


if __name__ == "__main__":
    app()
