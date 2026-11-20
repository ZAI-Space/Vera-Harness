"""Persist GitHub marketplace catalogs, immutable packages and explicit activation state."""

import json
import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from vera.plugins.manifest import load_bundle, read_json
from vera.plugins.source import (
    PluginError,
    PluginSource,
    filesystem_path,
    inventory,
    normalize_source,
    open_source,
    relative_path,
)


def _name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value) or len(value) > 48:
        raise PluginError(
            "Names must use up to 48 lowercase letters, digits and single hyphens, starting with a letter."
        )
    return value


def _digest(files: dict[str, str]) -> str:
    return sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# The Gitee revision retains plugin files locally; newer catalogs redirect to GitHub.
BUILTIN_MARKETPLACES = {
    PluginSource.github: ("openai/plugins", "HEAD", "openai-curated"),
    PluginSource.gitee: ("mirrors/claude-code", "1718a574950cd8979b27b3e21f5e82760b10e8e0", "claude-code-plugins"),
}


class PluginManager:
    """Manage one user-owned plugin store; operations never run downloaded code.

    SQLite serializes mutations across processes. Packages are content-addressed;
    a failed fetch/validation leaves the active revision untouched. Uninstall removes
    registration, retaining cached objects so already running sessions keep their files.
    """

    def __init__(self, directory: Path):
        self.directory = filesystem_path(directory)
        self.database = self.directory / "registry.sqlite3"

    @contextmanager
    def _state(self, *, write: bool = False) -> Iterator[dict]:
        empty = {"schema": 1, "marketplaces": {}, "plugins": {}}
        if not self.database.exists() and not write:
            yield empty
            return
        if write:
            self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.database, timeout=5)) as connection, connection:
                if write:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS registry (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
                    )
                    connection.commit()
                    connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT value FROM registry WHERE id = 1").fetchone()
                state = json.loads(row[0]) if row else empty
                if (
                    not isinstance(state, dict)
                    or state.get("schema") != 1
                    or not isinstance(state.get("plugins"), dict)
                    or not isinstance(state.get("marketplaces"), dict)
                ):
                    raise PluginError("Unsupported or corrupt plugin registry schema.")
                yield state
                if write:
                    connection.execute(
                        "INSERT OR REPLACE INTO registry (id, value) VALUES (1, ?)", (json.dumps(state),)
                    )
        except (sqlite3.Error, json.JSONDecodeError) as error:
            raise PluginError(f"Plugin registry unavailable: {type(error).__name__}.") from None

    def list_plugins(self) -> dict:
        """Return installed identities, active versions, approval state and retained history."""
        with self._state() as state:
            return state["plugins"]

    def list_marketplaces(self) -> dict:
        """Return saved catalogs without fetching or executing anything."""
        with self._state() as state:
            return state["marketplaces"]

    def selected_marketplace(self) -> str | None:
        """Return the saved user selection; selection never changes plugin activation state."""
        with self._state() as state:
            return state.get("selected_marketplace")

    def use_marketplace(self, source: PluginSource, *, refresh: bool = True) -> dict:
        """Fetch one of two built-in markets and select it for subsequent named installations.

        A failed fetch preserves the prior selection. Gitee uses a fixed, verified
        snapshot whose same-repository packages download entirely from Gitee.
        """
        source = PluginSource(source)
        repository, ref, name = BUILTIN_MARKETPLACES[source]
        existing = self.list_marketplaces()
        catalog = (
            self.add_marketplace(repository, ref, host=source, replace=name if name in existing else None)
            if refresh or name not in existing
            else {"name": name, **existing[name]}
        )
        if catalog["name"] != name:
            raise PluginError("The built-in marketplace changed its declared identity.")
        with self._state(write=True) as state:
            state["selected_marketplace"] = name
        return {
            "source": source.value,
            "marketplace": name,
            "commit": catalog["commit"],
            "plugins": len(catalog["plugins"]),
        }

    def install_named(self, name: str) -> dict:
        """Install a name from the selected built-in market; no addresses or config files are needed."""
        selected = self.selected_marketplace()
        if selected is None:
            raise PluginError("Choose a source first: plugins marketplace use github (or gitee).")
        return self.install_from_marketplace(name, selected)

    def add_marketplace(
        self, source: str, ref: str = "HEAD", *, host: PluginSource = PluginSource.github, replace: str | None = None
    ) -> dict:
        """Fetch a Codex/Claude repository marketplace and atomically save validated entries.

        Same-repository entries are pinned to the catalog's commit. External GitHub
        entries retain their declared ref/sha until installation resolves it to a commit.
        """
        # Fetch and validate before taking a database write lock. A slow Git
        # download must not block another marketplace or plugin mutation.
        with open_source(normalize_source(source, host), ref) as fetched:
            with TemporaryDirectory(prefix="vera-marketplace-") as temporary:
                catalog_path = next(
                    (
                        path
                        for path in (".agents/plugins", ".claude-plugin")
                        if fetched.contains(f"{path}/marketplace.json")
                    ),
                    None,
                )
                if catalog_path is None:
                    raise PluginError("Missing .agents/plugins/marketplace.json or .claude-plugin/marketplace.json.")
                root = fetched.export(catalog_path, Path(temporary).resolve() / "catalog")
                catalog = read_json(root / "marketplace.json")
            name = _name(catalog.get("name", ""))
            if replace is not None and name != replace:
                raise PluginError("Marketplace refresh cannot change its identity.")
            entries = catalog.get("plugins")
            if not isinstance(entries, list) or len(entries) > 1000:
                raise PluginError("Marketplace must contain a plugins array with at most 1,000 entries.")
            plugins = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise PluginError("Marketplace entries must be objects.")
                plugin_name = _name(entry.get("name", ""))
                if plugin_name in plugins:
                    raise PluginError(f"Duplicate marketplace plugin: {plugin_name}.")
                origin = entry.get("source")
                if isinstance(origin, str):
                    origin = {"source": "local", "path": origin}
                if not isinstance(origin, dict):
                    raise PluginError(f"Missing source for marketplace plugin {plugin_name!r}.")
                kind = origin.get("source")
                if kind == "local":
                    specification = {"source": fetched.location, "ref": fetched.commit or ref}
                elif kind in {"url", "git-subdir", "github", "git"}:
                    specification = {
                        "source": normalize_source(
                            origin.get("repo", "") if kind == "github" else origin.get("url", "")
                        ),
                        "ref": origin.get("sha", origin.get("ref", "HEAD")),
                    }
                    if not specification["source"].startswith(("https://github.com/", "https://gitee.com/")):
                        raise PluginError("Remote catalog entries must reference GitHub or Gitee HTTPS repositories.")
                    if (
                        not isinstance(specification["ref"], str)
                        or not specification["ref"]
                        or specification["ref"].startswith("-")
                    ):
                        raise PluginError("Marketplace refs must be nonempty Git ref strings.")
                else:
                    # Show unsupported entries without pretending they can be installed.
                    plugins[plugin_name] = {"unsupported": f"Unsupported marketplace source: {kind!r}."}
                    continue
                specification["path"] = relative_path(origin.get("path", "."))
                policy = entry.get("policy", {})
                if not isinstance(policy, dict):
                    raise PluginError("Marketplace policy must be an object.")
                if policy.get("installation") == "NOT_AVAILABLE":
                    specification["unsupported"] = "Marketplace policy marks this plugin NOT_AVAILABLE."
                plugins[plugin_name] = specification
            record = {
                "source": fetched.location,
                "ref": ref,
                "commit": fetched.commit,
                "catalog": f"{catalog_path}/marketplace.json",
                "plugins": plugins,
            }
            with self._state(write=True) as state:
                if replace is None and name in state["marketplaces"]:
                    raise PluginError(f"Marketplace {name!r} already exists; use marketplace refresh.")
                state["marketplaces"][name] = record
            return {"name": name, **record}

    def refresh_marketplace(self, name: str) -> dict:
        """Refresh one catalog from its saved source; a failure preserves the last catalog."""
        markets = self.list_marketplaces()
        if name not in markets:
            raise PluginError(f"Unknown marketplace {name!r}.")
        record = markets[name]
        return self.add_marketplace(record["source"], record["ref"], replace=name)

    def remove_marketplace(self, name: str) -> None:
        """Remove catalog registration; explicitly installed plugins remain usable."""
        with self._state(write=True) as state:
            if name not in state["marketplaces"]:
                raise PluginError(f"Unknown marketplace {name!r}.")
            del state["marketplaces"][name]
            if state.get("selected_marketplace") == name:
                state.pop("selected_marketplace")

    def _install(self, state: dict, source: str, ref: str, path: str, *, expected: str | None = None) -> dict:
        with open_source(source, ref) as fetched:
            objects = self.directory / "objects"
            objects.mkdir(exist_ok=True)
            with TemporaryDirectory(prefix=".install-", dir=objects) as temporary:
                candidate = fetched.export(path, Path(temporary).resolve() / "package")
                bundle = load_bundle(candidate)
                name = bundle.manifest.name
                if expected is not None and name != expected:
                    raise PluginError(f"Expected plugin {expected!r}, received {name!r}.")
                files = inventory(candidate)
                digest = _digest(files)
                destination = objects / digest
                if destination.exists():
                    if inventory(destination) != files:
                        raise PluginError("An installed package failed its integrity check.")
                else:
                    os.rename(candidate, destination)
            record = {
                **bundle.manifest.model_dump(),
                "source": fetched.location,
                "ref": ref,
                "path": relative_path(path),
                "commit": fetched.commit,
                "digest": digest,
            }
            plugin = state["plugins"].setdefault(name, {"active": digest, "enabled": False, "versions": {}})
            if plugin["active"] != digest:
                plugin["enabled"] = False
            plugin["versions"][digest] = record
            plugin["active"] = digest
            return {**record, "enabled": plugin["enabled"]}

    def install(
        self, source: str, ref: str = "HEAD", path: str = ".", *, host: PluginSource = PluginSource.github
    ) -> dict:
        """Install a local/GitHub package disabled; an update with changed files revokes activation."""
        with self._state(write=True) as state:
            result = self._install(state, normalize_source(source, host), ref, path)
            state["plugins"][result["name"]].pop("marketplace", None)
            return result

    def install_from_marketplace(self, plugin: str, marketplace: str) -> dict:
        """Install an advertised plugin from the last saved catalog, checking its declared identity."""
        with self._state(write=True) as state:
            market = state["marketplaces"].get(marketplace)
            if market is None or plugin not in market["plugins"]:
                raise PluginError(f"Unknown marketplace plugin {plugin}@{marketplace}.")
            entry = market["plugins"][plugin]
            if entry.get("unsupported"):
                raise PluginError(entry["unsupported"])
            result = self._install(state, entry["source"], entry["ref"], entry["path"], expected=plugin)
            state["plugins"][plugin]["marketplace"] = marketplace
            return result

    def update(self, name: str, ref: str | None = None) -> dict:
        """Resolve the saved source again; marketplace packages use its explicitly refreshed catalog."""
        with self._state(write=True) as state:
            plugin = self._plugin(state, name)
            record = plugin["versions"][plugin["active"]]
            if market_name := plugin.get("marketplace"):
                market = state["marketplaces"].get(market_name)
                if market is None or name not in market["plugins"]:
                    raise PluginError("The plugin's marketplace is unavailable; add/refresh it before updating.")
                entry = market["plugins"][name]
                if entry.get("unsupported"):
                    raise PluginError(entry["unsupported"])
                if ref is not None:
                    raise PluginError(
                        "Refresh the marketplace to update a catalog-pinned plugin; --ref is for direct installs."
                    )
                return self._install(state, entry["source"], entry["ref"], entry["path"], expected=name)
            return self._install(state, record["source"], ref or record["ref"], record["path"], expected=name)

    @staticmethod
    def _plugin(state: dict, name: str) -> dict:
        if name not in state["plugins"]:
            raise PluginError(f"Unknown installed plugin {name!r}.")
        return state["plugins"][name]

    def package(self, record: dict) -> Path:
        """Verify an installed version before inspecting, enabling or loading its declarations."""
        digest = record["digest"]
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise PluginError("Invalid installed package digest.")
        path = self.directory / "objects" / digest
        if not path.is_dir() or path.resolve() != path or _digest(inventory(path)) != digest:
            raise PluginError(f"Plugin integrity check failed: {record['name']}.")
        return path

    def show(self, name: str) -> dict:
        """Describe the selected revision, actual commands/endpoints and historical digests."""
        with self._state() as state:
            plugin = self._plugin(state, name)
            record = plugin["versions"][plugin["active"]]
            return {
                **record,
                **load_bundle(self.package(record)).describe(),
                "enabled": plugin["enabled"],
                "versions": plugin["versions"],
            }

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Approve the current digest or revoke future loading; existing runs keep their snapshot."""
        with self._state(write=True) as state:
            plugin = self._plugin(state, name)
            if enabled:
                load_bundle(self.package(plugin["versions"][plugin["active"]]))
            plugin["enabled"] = enabled

    def rollback(self, name: str, digest: str) -> dict:
        """Select a retained exact version and disable it pending explicit activation."""
        with self._state(write=True) as state:
            plugin = self._plugin(state, name)
            if digest not in plugin["versions"]:
                raise PluginError("Rollback requires a full digest from this plugin's version history.")
            record = plugin["versions"][digest]
            self.package(record)
            plugin.update(active=digest, enabled=False)
            return record

    def uninstall(self, name: str) -> None:
        """Remove plugin registration/history; retain cached files for running sessions."""
        with self._state(write=True) as state:
            self._plugin(state, name)
            del state["plugins"][name]
