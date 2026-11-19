"""Planning-only capabilities: bounded project inspection and one host-owned Markdown artifact."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from minisweagent.exceptions import Submitted
from minisweagent.terminal.files import ProjectFiles
from minisweagent.tools import ToolError, ToolRegistry, ToolSpec


def plan_prompt(request: str) -> str:
    """Build the Hermes-style single-turn planning request; implementation requires a later user task."""
    return (
        "[/plan: planning only]\nInspect relevant project files if necessary. Do not implement the task, "
        "run shell commands, change project source, commit, or invoke external mutations. "
        "Produce a Markdown plan covering the goal, current implementation, exact files to change, "
        "small implementation steps, verification commands and expected results, risks and open questions. "
        "Use plan_finish to save the complete plan. Do not execute it after saving.\n\nRequest:\n" + request
    )


def plan_registry(workspace: Path) -> ToolRegistry:
    """Replace execution capabilities with file inspection and a confined plan writer.

    No Bash, MCP, plugins or Subagents are exposed. Project file rules also exclude
    credentials, traversal and escaping links. Only plan_finish may write a file.
    """
    files = ProjectFiles(workspace)
    registry = ToolRegistry()

    def list_files(arguments):
        return {"output": "\n".join(files.list(arguments.get("query", ""))), "returncode": 0, "exception_info": ""}

    def read_file(arguments):
        return {"output": files.attach("", [arguments["path"]]), "returncode": 0, "exception_info": ""}

    def finish(arguments):
        directory = files.root / ".vera" / "plans"
        if directory.resolve() != directory:
            raise ToolError("Plan directory cannot be a symlink or junction.")
        directory.mkdir(parents=True, exist_ok=True)
        if directory.resolve() != directory:
            raise ToolError("Plan directory changed; refusing to write outside the project.")
        path = directory / f"{datetime.now(timezone.utc):%Y-%m-%d_%H%M%S}-{uuid4().hex[:8]}.md"
        with path.open("x", encoding="utf-8") as stream:
            stream.write(arguments["markdown"])
        summary = f"Plan saved: {path}\n\n{arguments['markdown']}"
        raise Submitted(
            {
                "role": "exit",
                "content": summary,
                "extra": {"exit_status": "Submitted", "submission": summary, "plan_path": str(path)},
            }
        )

    registry.register(
        ToolSpec(
            "project_files",
            "Find project file paths to inspect.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "additionalProperties": False},
        ),
        list_files,
    )
    registry.register(
        ToolSpec(
            "project_read",
            "Read a non-sensitive project text file.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        read_file,
    )
    registry.register(
        ToolSpec(
            "plan_finish",
            "Save the complete Markdown implementation plan and end this planning task.",
            {
                "type": "object",
                "properties": {"markdown": {"type": "string", "minLength": 1, "maxLength": 100_000}},
                "required": ["markdown"],
                "additionalProperties": False,
            },
        ),
        finish,
    )
    return registry
