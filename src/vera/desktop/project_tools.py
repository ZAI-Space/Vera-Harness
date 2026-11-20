"""Desktop project inspection tools reuse the terminal's confined file rules."""

from pathlib import Path

from vera.modes.plan import plan_registry
from vera.terminal.files import MAX_FILE_BYTES, ProjectFiles
from vera.tools import ToolSpec


def register_project_tools(registry, workspace: Path) -> None:
    """Register bounded read/search handlers; never grant write or shell permission."""
    existing = {row["function"]["name"] for row in registry.definitions()}
    read_only = plan_registry(workspace).select(["project_files", "project_read"])
    for row in read_only.definitions():
        definition = row["function"]
        name = definition["name"]
        if name not in existing:
            registry.register(
                ToolSpec(**definition),
                lambda arguments, name=name: read_only.execute({"tool": name, "arguments": arguments}),
            )

    def search(arguments):
        files = ProjectFiles(workspace)
        results = []
        query = arguments["query"].casefold()
        for name in files.list(limit=80):
            path = files.resolve(name)
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                continue
            if "\x00" in text:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if query in line.casefold():
                    results.append(f"{name}:{number}: {line[:300]}")
                    if len(results) >= 80:
                        break
            if len(results) >= 80:
                break
        return {"output": "\n".join(results), "returncode": 0, "exception_info": ""}

    if "project_search" not in existing:
        registry.register(
            ToolSpec(
                "project_search",
                "Search literal text in up to 80 allowed UTF-8 project files; results are bounded.",
                {
                    "type": "object",
                    "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 300}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            search,
        )
