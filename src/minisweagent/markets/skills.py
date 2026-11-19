"""Discover on skills.sh and install validated, pinned GitHub skill snapshots without hooks."""

import json
import re
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from minisweagent import global_config_dir
from minisweagent.channels.credentials import private_directory
from minisweagent.evolution.process import experiment_lock, write_json
from minisweagent.markets.http import catalog_json
from minisweagent.plugins.source import Source, inventory, open_source
from minisweagent.tools import ToolError
from minisweagent.tools.skills import discover_skill_roots

_IDENTIFIER = re.compile(r"((?!\.{1,2}/)[A-Za-z0-9_.-]+/(?!\.{1,2}/)[A-Za-z0-9_.-]+)/([a-z0-9]+(?:-[a-z0-9]+)*)")


class SkillMarket:
    """One default source, skills.sh; download content from its underlying GitHub revision."""

    def __init__(self, endpoint: str = "https://skills.sh"):
        self.endpoint = endpoint.rstrip("/")

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Return canonical owner/repo/skill identifiers and publisher metadata."""
        value = catalog_json(self.endpoint + "/api/search", params={"q": query, "limit": min(max(limit, 1), 100)})
        entries = []
        for item in value.get("skills", []):
            identifier = item.get("id", "")
            if not _IDENTIFIER.fullmatch(identifier):
                identifier = f"{item.get('source', '')}/{item.get('skillId', '')}"
            if _IDENTIFIER.fullmatch(identifier):
                entries.append(
                    {
                        "id": identifier,
                        "name": item.get("name", identifier.rsplit("/", 1)[-1]),
                        "repository": "https://github.com/" + identifier.rsplit("/", 1)[0],
                        "installs": item.get("installs", 0),
                    }
                )
        return entries[:limit]

    def install(self, identifier: str, *, directory: Path | None = None, ref: str = "HEAD") -> dict:
        """Fetch a single repository revision and install one skill; existing names are never replaced."""
        match = _IDENTIFIER.fullmatch(identifier)
        if not match:
            raise ToolError("Use a skills.sh owner/repo/skill identifier.")
        with open_source(match[1], ref) as source:
            return install_skill_snapshot(source, match[2], directory or global_config_dir / "skills")

    def inspect(self, identifier: str, *, ref: str = "HEAD") -> dict:
        """Fetch a disposable preview of instructions/assets and commit without installing a skill."""
        match = _IDENTIFIER.fullmatch(identifier)
        if not match:
            raise ToolError("Use a skills.sh owner/repo/skill identifier.")
        with open_source(match[1], ref) as source, TemporaryDirectory(prefix="vera-skill-preview-") as temporary:
            path, skill = _export_skill(source, match[2], Path(temporary) / match[2])
            return {
                "name": skill.name,
                "description": skill.description,
                "instructions": skill.view()["content"],
                "source": source.location,
                "commit": source.commit,
                "path": path,
                "files": inventory(skill.directory),
            }


def _export_skill(source: Source, name: str, destination: Path):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ToolError("Invalid skill name.")
    candidates = [
        path.rsplit("/", 1)[0]
        for path in source.files()
        if path.endswith(f"/{name}/SKILL.md") or path == f"{name}/SKILL.md"
    ]
    if source.contains("SKILL.md"):
        candidates.append(".")
    if len(candidates) != 1:
        raise ToolError("The repository must contain exactly one matching skill directory.")
    stage = source.export(candidates[0], destination)
    catalog = discover_skill_roots([stage])
    if set(catalog) != {name}:
        raise ToolError("Downloaded skill metadata must match its selected name.")
    catalog[name].view()
    return candidates[0], catalog[name]


def install_skill_snapshot(source: Source, name: str, directory: Path) -> dict:
    """Install a validated skill and its assets without executing package code.

    Export rejects traversal, links and oversized packages. Existing installations
    are never overwritten, including when their installed metadata differs.
    """
    directory = private_directory(Path(directory).expanduser().resolve())
    with TemporaryDirectory(prefix=".skill-stage-", dir=directory) as temporary:
        source_path, skill = _export_skill(source, name, Path(temporary) / name)
        stage = skill.directory
        content = skill.view()
        receipt = {
            "name": name,
            "source": source.location,
            "commit": source.commit,
            "path": source_path,
            "files": inventory(stage),
        }
        write_json(stage / ".vera-market.json", receipt)
        with experiment_lock(directory):
            destination = directory / name
            if destination.exists() or destination.is_symlink():
                raise ToolError("This skill is already installed; remove it explicitly before replacing it.")
            stage.rename(destination)
    return {
        "name": name,
        "description": skill.description,
        "directory": str(destination),
        "source": source.location,
        "commit": source.commit,
        "files": len(receipt["files"]),
        "instructions": content["content"],
    }


def remove_market_skill(name: str, directory: Path | None = None) -> None:
    """Remove only an unmodified market-owned skill; never delete a user's changed or local skill."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ToolError("Invalid skill name.")
    root = (directory or global_config_dir / "skills").expanduser().resolve()
    path = root / name
    if path.resolve() != path or not (path / ".vera-market.json").is_file():
        raise ToolError("Choose a market-installed skill.")
    with experiment_lock(root):
        receipt = json.loads((path / ".vera-market.json").read_text(encoding="utf-8"))
        current = {key: value for key, value in inventory(path).items() if key != ".vera-market.json"}
        if current != receipt["files"]:
            raise ToolError("This skill has local changes; preserve or remove it manually.")
        shutil.rmtree(path)
