"""User-authored global rules and memories, shared by runtime entry points."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from vera import global_config_dir
from vera.channels.credentials import private_directory
from vera.evolution.process import experiment_lock, read_json, write_json

DEFAULT_DIRECTORY = global_config_dir / "user-context"


class UserContext:
    """Manage explicit user instructions; never infer or write memories automatically.

    Enabled content applies to all projects using this profile on the next task.
    Markdown/Jinja-looking content is inserted as a value, never as a template.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY):
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / "entries.json"

    def entries(self) -> list[dict]:
        """Return detached entries; malformed persisted state raises a clear ValueError."""
        if not self.path.exists():
            return []
        try:
            value = read_json(self.path)
            rows = value.get("entries", []) if isinstance(value, dict) else None
            if not isinstance(rows, list):
                raise ValueError("Expected an entry list.")
            for row in rows:
                self._validate_entry(row)
                if not isinstance(row.get("id"), str) or not row["id"].strip() or "enabled" not in row:
                    raise ValueError("Missing entry identifier or enabled state.")
            if len({row["id"] for row in rows}) != len(rows):
                raise ValueError("Duplicate entry identifiers.")
        except ValueError as error:
            raise ValueError("用户规则文件格式无效，请检查 entries.json 后重试。") from error
        return rows

    @staticmethod
    def _validate_entry(entry: dict) -> None:
        """Reject malformed input before persistence or downstream field access."""
        if not isinstance(entry, dict):
            raise ValueError("条目格式无效。")
        identifier = entry.get("id")
        if identifier is not None and (not isinstance(identifier, str) or not identifier.strip()):
            raise ValueError("条目标识无效，请刷新后重试。")
        kind, title, content = entry.get("kind"), entry.get("title"), entry.get("content")
        if kind not in ("rule", "memory") or not isinstance(title, str) or not 1 <= len(title.strip()) <= 128:
            raise ValueError("请选择规则或记忆，并填写 1～128 字的标题。")
        if (
            not isinstance(content, str)
            or not 1 <= len(content.strip()) <= 16000
            or not isinstance(entry.get("enabled", True), bool)
        ):
            raise ValueError("内容须为 1～16000 字，启用状态须为布尔值。")

    def save(self, entry: dict) -> dict:
        """Create/update a bounded entry atomically; invalid input raises ValueError."""
        self._validate_entry(entry)
        kind, title, content = entry["kind"], entry["title"], entry["content"]
        private_directory(self.directory)
        with experiment_lock(self.directory):
            rows = self.entries()
            identifier = entry.get("id")
            if identifier and identifier not in {row["id"] for row in rows}:
                raise ValueError("该条目已不存在，请刷新后重试。")
            saved = {
                "id": identifier or uuid4().hex,
                "kind": kind,
                "title": title.strip(),
                "content": content.strip(),
                "enabled": entry.get("enabled", True),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            rows = [saved if row["id"] == identifier else row for row in rows] if identifier else [*rows, saved]
            if len(rows) > 128 or sum(len(row["content"]) for row in rows if row["enabled"]) > 64000:
                raise ValueError("最多保存 128 个条目，已启用的总内容不能超过 64000 字。")
            write_json(self.path, {"version": 1, "entries": rows})
            return deepcopy(saved)

    def remove(self, identifier: str) -> None:
        """Delete only the selected entry; already-running tasks retain their context snapshot."""
        private_directory(self.directory)
        with experiment_lock(self.directory):
            rows = self.entries()
            if identifier not in {row["id"] for row in rows}:
                raise ValueError("该条目已不存在，请刷新后重试。")
            write_json(self.path, {"version": 1, "entries": [row for row in rows if row["id"] != identifier]})

    def render(self) -> str:
        """Render user-maintained preferences separately from remembered facts."""
        rows = [row for row in self.entries() if row["enabled"]]
        sections = []
        for kind, heading in (("rule", "User global rules"), ("memory", "User-maintained global memory")):
            selected = [f"### {row['title']}\n{row['content']}" for row in rows if row["kind"] == kind]
            if selected:
                sections.append(f"## {heading}\n" + "\n\n".join(selected))
        return "\n\n".join(sections)


def apply_user_context(agent, content: str) -> None:
    """Append a literal context value to the agent template and expose it to delegated agents."""
    if content:
        agent.config.system_template += "\n\n{{ user_global_context }}"
        agent.extra_template_vars["user_global_context"] = content
