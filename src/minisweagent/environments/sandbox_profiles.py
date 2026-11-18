"""Persist user-configured sandboxes and expose availability without provisioning them."""

import json
import re
import sqlite3
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from minisweagent import global_config_dir
from minisweagent.environments.sandbox import SandboxConfig, SandboxMode, _bubblewrap, _docker
from minisweagent.tools import ToolError


class SandboxProfileSettings(BaseModel):
    """Locate the user-owned store; opening a missing store for reading creates nothing."""

    model_config = ConfigDict(extra="forbid")
    path: Path = global_config_dir / "sandbox-profiles.sqlite3"


def _name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name) or name in {"none", "local", "all"}:
        raise ToolError(
            "Use a sandbox name starting with a letter, up to 48 lowercase letters, digits or hyphens; none/local/all are reserved."
        )
    return name


class SandboxProfiles:
    """Manage named Docker/Bubblewrap profiles, without installing or starting containers.

    SQLite transactions serialize updates across terminal and desktop processes.
    Workspace paths are bound to the current project when supplied to check/select;
    otherwise an explicitly saved workspace is used. Invalid changes leave the
    existing profile untouched. Corrupt or inaccessible stores raise ToolError.
    """

    def __init__(self, path: Path | None = None):
        self.path = (path if path is not None else SandboxProfileSettings().path).expanduser().resolve()

    @classmethod
    def from_config(cls, config: dict) -> "SandboxProfiles":
        """Resolve store settings from the same config used by the agent runtime."""
        return cls(SandboxProfileSettings.model_validate(config.get("sandbox_profiles", {})).path)

    def list_profiles(self) -> dict[str, SandboxConfig]:
        """Return validated configuration copies, with no engine detection or disk writes."""
        if not self.path.exists():
            return {}
        try:
            with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=5)) as connection:
                rows = connection.execute("SELECT name, config FROM profiles ORDER BY name").fetchall()
            return {_name(name): self._validate(json.loads(value)) for name, value in rows}
        except (sqlite3.Error, json.JSONDecodeError) as error:
            raise ToolError(f"Sandbox profile store unavailable: {type(error).__name__}.") from None

    @staticmethod
    def _validate(config: dict) -> SandboxConfig:
        value = SandboxConfig.model_validate(config)
        if value.mode not in {SandboxMode.DOCKER, SandboxMode.BUBBLEWRAP}:
            raise ToolError("Named sandboxes require an explicit docker or bubblewrap backend.")
        return value

    def save(self, name: str, config: dict, *, replace: bool = False) -> dict:
        """Add a profile or explicitly replace it; no engine or image is downloaded.

        Relative workspace paths are saved as absolute paths at configuration time.
        Engine availability is checked separately, so offline configurations can be saved.
        """
        name = _name(name)
        profile = self._validate(config)
        profile.workspace = profile.workspace.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
                connection.execute("CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, config TEXT NOT NULL)")
                connection.execute("BEGIN IMMEDIATE")
                if not replace and connection.execute("SELECT 1 FROM profiles WHERE name = ?", (name,)).fetchone():
                    raise ToolError("Sandbox profile already exists; explicitly request replacement.")
                connection.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?)", (name, profile.model_dump_json()))
        except sqlite3.Error as error:
            raise ToolError(f"Cannot save sandbox profile: {type(error).__name__}.") from None
        return {"name": name, "config": profile.model_dump(mode="json")}

    def remove(self, name: str) -> None:
        """Delete a saved profile; running tasks retain their already assembled environment."""
        name = _name(name)
        if not self.path.exists():
            raise ToolError(f"Unknown sandbox profile: {name!r}.")
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as connection, connection:
                if not connection.execute("DELETE FROM profiles WHERE name = ?", (name,)).rowcount:
                    raise ToolError(f"Unknown sandbox profile: {name!r}.")
        except sqlite3.Error as error:
            raise ToolError(f"Cannot remove sandbox profile: {type(error).__name__}.") from None

    def select(self, name: str, workspace: Path | None = None) -> SandboxConfig:
        """Return a detached profile bound to a project; unknown names fail without fallback."""
        profiles = self.list_profiles()
        if name not in profiles:
            raise ToolError(f"Unknown sandbox profile: {name!r}.")
        profile = profiles[name]
        profile.workspace = (workspace if workspace is not None else profile.workspace).expanduser().resolve()
        return profile

    def check(self, name: str, workspace: Path | None = None) -> dict:
        """Probe the workspace/engine/image without downloads or container creation.

        Bubblewrap performs a bounded namespace probe. Status is a snapshot, not a
        guarantee of later startup; open_runtime rechecks and never falls back to local.
        """
        return self._availability(name, self.select(name, workspace))

    @staticmethod
    def _availability(name: str, profile: SandboxConfig) -> dict:
        available, code, reason = False, "workspace_unavailable", "Project directory does not exist."
        if profile.workspace.is_dir():
            available = (
                _docker(profile) is not None if profile.mode == SandboxMode.DOCKER else _bubblewrap() is not None
            )
            code = "available" if available else "backend_unavailable"
            reason = (
                "Ready."
                if available
                else (
                    "A local Linux Docker engine must be running and the configured image must already be cached."
                    if profile.mode == SandboxMode.DOCKER
                    else "Bubblewrap requires a Linux/WSL process, an installed bwrap executable and working namespaces."
                )
            )
        return {"name": name, "backend": profile.mode.value, "available": available, "code": code, "reason": reason}

    def status(self, workspace: Path | None = None) -> dict:
        """Return frontend-ready configured/available flags and reasons for disabled choices."""
        choices = []
        for name, profile in self.list_profiles().items():
            if workspace is not None:
                profile.workspace = workspace.expanduser().resolve()
            choices.append(self._availability(name, profile))
        enabled = any(row["available"] for row in choices)
        return {
            "configured": bool(choices),
            "enabled": enabled,
            "reason": ""
            if enabled
            else "No available configured sandbox."
            if choices
            else "Configure a sandbox in settings first.",
            "choices": choices,
        }


def resolve_sandbox_profile(config: dict, workspace: Path | None = None) -> dict:
    """Apply an explicitly selected saved profile to a copied runtime configuration.

    The current project overrides a saved workspace when provided. Profile fields
    replace the entire sandbox configuration, preventing stale permissions/image
    settings from another profile from carrying over. No selection preserves legacy behavior.
    """
    result = deepcopy(config)
    name = result.get("sandbox_profile")
    if name is not None:
        if not isinstance(name, str) or not name:
            raise ToolError("sandbox_profile must be a configured sandbox name.")
        result["sandbox"] = SandboxProfiles.from_config(result).select(name, workspace).model_dump(mode="json")
    return result
