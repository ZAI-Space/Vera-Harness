"""Discover local Agent Skills and read their instructions and supporting files on demand."""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TextIO

import yaml
from pydantic import BaseModel, ConfigDict, Field

from vera import global_config_dir
from vera.tools import ToolError, ToolRegistry, ToolSpec

_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_HEADER_LIMIT = 16_384
_DOCUMENT_LIMIT = 24_000
_PAGE_SIZE = 6
_CONTENT_PAGE_SIZE = 3500
_MAX_FILES = 24
_SUPPORT_DIRS = ("references", "templates", "scripts", "assets")
_TEXT_SUFFIXES = {".md", ".txt", ".py", ".sh", ".ps1", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".csv", ".html"}


class SkillConfig(BaseModel):
    """Configure local discovery, extra roots and skills hidden from the current run."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    directories: list[Path] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)


def _read_metadata(reader: TextIO) -> tuple[str, str]:
    if reader.readline(_HEADER_LIMIT).rstrip("\r\n") != "---":
        raise ToolError("Expected YAML frontmatter at the start of SKILL.md.")
    lines = []
    remaining = _HEADER_LIMIT
    while remaining:
        line = reader.readline(remaining)
        remaining -= len(line)
        if line.rstrip("\r\n") == "---":
            break
        if not line:
            raise ToolError("Missing closing delimiter in SKILL.md frontmatter.")
        lines.append(line)
    else:
        raise ToolError("SKILL.md frontmatter exceeds its size limit.")
    try:
        metadata = yaml.safe_load("".join(lines))
    except yaml.YAMLError:
        raise ToolError("Invalid YAML in SKILL.md frontmatter.") from None
    if not isinstance(metadata, dict):
        raise ToolError("SKILL.md frontmatter must be a mapping.")
    name, description = metadata.get("name"), metadata.get("description")
    if not isinstance(name, str) or len(name) > 64 or not _NAME.fullmatch(name):
        raise ToolError("Skill name must use up to 64 lowercase letters, digits and single hyphens.")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise ToolError("Skill description must contain between 1 and 1024 characters.")
    return name, description.strip()


def _resolve_file(root: Path, relative: Path) -> Path:
    path = root / relative
    if path.resolve() != path or not path.is_file():
        raise ToolError(f"Skill file is unavailable: {relative.as_posix()!r}.")
    return path


def _walk(root: Path, *, stop_at_skill: bool = False) -> Iterator[Path]:
    """Walk directories below a root without traversing symlinks or junctions."""
    pending = [root]
    while pending:
        directory = pending.pop()
        yield directory
        if stop_at_skill and (directory / "SKILL.md").is_file():
            continue
        children = sorted(directory.iterdir(), reverse=True)
        pending.extend(
            child
            for child in children
            if not child.name.startswith(".") and child.is_dir() and child.resolve() == child
        )


@dataclass(frozen=True)
class Skill:
    """An indexed skill with UTF-8 instructions and optional text attachments."""

    name: str
    description: str
    directory: Path

    def view(self, file_path: str | None = None) -> dict:
        """Return a skill body or a named attachment. Raise ToolError for unavailable content."""
        try:
            if file_path is not None:
                relative = PurePosixPath(file_path)
                windows = PureWindowsPath(file_path)
                if (
                    relative.is_absolute()
                    or windows.drive
                    or "\\" in file_path
                    or ":" in file_path
                    or len(relative.parts) < 2
                    or relative.parts[0] not in _SUPPORT_DIRS
                    or any(part.startswith(".") for part in relative.parts)
                    or relative.suffix.lower() not in _TEXT_SUFFIXES
                ):
                    raise ToolError("Use a relative text file under references/, templates/, scripts/ or assets/.")
                source = _resolve_file(self.directory, Path(*relative.parts))
                with source.open(encoding="utf-8-sig") as reader:
                    content = reader.read(_DOCUMENT_LIMIT + 1)
                if len(content) > _DOCUMENT_LIMIT:
                    content = content[:_DOCUMENT_LIMIT] + "\n[Skill attachment truncated]"
                return {"name": self.name, "file_path": relative.as_posix(), "content": content}

            source = _resolve_file(self.directory, Path("SKILL.md"))
            with source.open(encoding="utf-8-sig") as reader:
                if _read_metadata(reader)[0] != self.name:
                    raise ToolError(f"Skill {self.name!r} was renamed. Reload the catalog.")
                content = reader.read(_DOCUMENT_LIMIT + 1)
            if len(content) > _DOCUMENT_LIMIT:
                raise ToolError(
                    f"Skill {self.name!r} exceeds {_DOCUMENT_LIMIT} characters. Move detail into attachments."
                )
            attachments = []
            for folder in _SUPPORT_DIRS:
                root = self.directory / folder
                if root.is_dir() and root.resolve() == root:
                    for directory in _walk(root):
                        for path in sorted(directory.iterdir()):
                            if (
                                path.suffix.lower() in _TEXT_SUFFIXES
                                and not path.name.startswith(".")
                                and path.is_file()
                                and path.resolve() == path
                            ):
                                attachments.append(path.relative_to(self.directory).as_posix())
            return {
                "name": self.name,
                "content": content,
                "directory": str(self.directory),
                "files": attachments[:_MAX_FILES],
                "files_total": len(attachments),
            }
        except ToolError:
            raise
        except (OSError, ValueError, RuntimeError) as error:
            raise ToolError(f"Could not read skill {self.name!r} ({type(error).__name__}).") from None


def discover_skill_roots(roots: list[Path], disabled: list[str] = ()) -> dict[str, Skill]:
    """Index only the supplied roots; earlier roots take precedence, without global discovery."""
    skills = {}
    try:
        for root in dict.fromkeys(roots):
            resolved_root = root.resolve()
            if not resolved_root.exists():
                continue
            if not resolved_root.is_dir():
                raise ToolError(f"Skill root is not a directory: {root}.")
            for directory in _walk(resolved_root, stop_at_skill=True):
                source = directory / "SKILL.md"
                if not source.is_file() or source.resolve() != source:
                    continue
                with source.open(encoding="utf-8-sig") as reader:
                    try:
                        name, description = _read_metadata(reader)
                    except ToolError as error:
                        raise ToolError(f"{source}: {error}") from None
                if name != directory.name:
                    raise ToolError(f"{source}: skill name must match the containing directory.")
                if name not in disabled:
                    skills.setdefault(name, Skill(name, description, directory))
    except (OSError, UnicodeError, RuntimeError) as error:
        raise ToolError(f"Skill discovery failed ({type(error).__name__}).") from None
    return dict(sorted(skills.items()))


def discover_skills(config: SkillConfig, workspace: Path) -> dict[str, Skill]:
    """Index project, configured and user skill roots. Earlier roots take precedence."""
    if not config.enabled:
        return {}
    workspace = workspace.resolve()
    project_root = workspace / ".agents" / "skills"
    roots = [project_root] if project_root.resolve() == project_root else []
    roots.extend(workspace / path.expanduser() for path in config.directories)
    return discover_skill_roots([*roots, global_config_dir / "skills"], config.disabled)


def get_skill(skills: dict[str, Skill], name: str) -> Skill:
    """Find an enabled skill by its catalog name or raise ToolError."""
    if name not in skills:
        raise ToolError(f"Unknown skill {name!r}. Use skills_list to see available skills.")
    return skills[name]


def register_skill_tools(registry: ToolRegistry, skills: dict[str, Skill]) -> None:
    """Expose the catalog and skill documents via the existing model tool registry."""

    def list_skills(arguments: dict) -> dict:
        query = arguments.get("query", "").casefold()
        offset = int(arguments.get("offset", 0))
        matches = [
            {"name": skill.name, "description": skill.description}
            for skill in skills.values()
            if query in skill.name or query in skill.description.casefold()
        ]
        next_offset = offset + _PAGE_SIZE
        return {
            "output": json.dumps(
                {
                    "skills": matches[offset:next_offset],
                    "next_offset": next_offset if next_offset < len(matches) else None,
                },
                ensure_ascii=False,
            ),
            "returncode": 0,
            "exception_info": "",
        }

    def view_skill(arguments: dict) -> dict:
        result = get_skill(skills, arguments["name"]).view(arguments.get("file_path"))
        offset = int(arguments.get("offset", 0))
        content = result["content"]
        end = offset + _CONTENT_PAGE_SIZE
        result["content"] = content[offset:end]
        result["next_offset"] = end if end < len(content) else None
        return {"output": json.dumps(result, ensure_ascii=False), "returncode": 0, "exception_info": ""}

    registry.register(
        ToolSpec(
            "skills_list",
            "Discover workflows by name and description. Use next_offset to list more and skill_view to load a workflow.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
                "additionalProperties": False,
            },
        ),
        list_skills,
    )
    registry.register(
        ToolSpec(
            "skill_view",
            "Load a skill's instructions or a supporting text file. If next_offset is returned, request it before proceeding.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "file_path": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        view_skill,
    )
