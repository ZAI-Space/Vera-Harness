"""Enforce explicit read-only runtime capability boundaries, independently of UI choices."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from minisweagent.exceptions import Submitted
from minisweagent.tools import ToolSpec


class PermissionsConfig(BaseModel):
    """Standard preserves existing behavior; read-only disables Bash and all external MCP."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["standard", "read-only", "confirm", "auto"] = "standard"


class ReadOnlyEnvironment:
    """Delegate metadata/lifecycle while rejecting every legacy shell execution path."""

    def __init__(self, environment):
        self._environment = environment

    def __getattr__(self, name):
        return getattr(self._environment, name)

    def execute(self, action: dict) -> dict:
        """Return a rejected observation without invoking the underlying environment."""
        return {"output": "", "returncode": 1, "exception_info": "Read-only permissions prohibit Bash execution."}


def register_readonly_finish(registry) -> None:
    """Provide completion without a shell command for read-only native tool models."""

    def finish(arguments):
        raise Submitted(
            {
                "role": "exit",
                "content": arguments["summary"],
                "extra": {"exit_status": "Submitted", "submission": arguments["summary"]},
            }
        )

    registry.register(
        ToolSpec(
            "task_finish",
            "Complete this read-only task with the final answer.",
            {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
        ),
        finish,
    )
