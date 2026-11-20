"""Register model-callable tools and dispatch validated actions."""

import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable

from vera import Environment

BASH_PARAMETERS = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "The bash command to execute"}},
    "required": ["command"],
}


class ToolError(ValueError):
    """A validation or execution error that may be reported to the model."""


@dataclass(frozen=True)
class ToolSpec:
    """Name, model-facing description and JSON Schema for a tool's argument object."""

    name: str
    description: str
    parameters: dict


class ToolRegistry:
    """Per-agent registration of tool declarations and their execution handlers."""

    def __init__(self):
        self._tools: dict[str, tuple[ToolSpec, Callable[[dict], dict]]] = {}

    def register(self, spec: ToolSpec, handler: Callable[[dict], dict]) -> None:
        """Register a callable returning the environment output dict. Reject duplicate names or invalid schemas."""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", spec.name) or spec.name in self._tools:
            raise ToolError(f"Invalid or duplicate tool name: {spec.name!r}.")
        validator_for(spec.parameters).check_schema(spec.parameters)
        self._tools[spec.name] = deepcopy(spec), handler

    def definitions(self, *, responses: bool = False) -> list[dict]:
        """Return model-facing copies in Chat Completions or Responses API shape."""
        definitions = []
        for spec, _ in self._tools.values():
            function = {"name": spec.name, "description": spec.description, "parameters": deepcopy(spec.parameters)}
            definitions.append(
                {"type": "function", "strict": False, **function}
                if responses
                else {"type": "function", "function": function}
            )
        return definitions

    def select(self, names: list[str]) -> "ToolRegistry":
        """Create a registry containing only these tools, with the same execution handlers."""
        if missing := set(names) - self._tools.keys():
            raise ToolError(f"Tools unavailable in this runtime: {', '.join(sorted(missing))}.")
        selected = ToolRegistry()
        selected._tools = {name: self._tools[name] for name in names}
        return selected

    def validate(self, name: object, arguments: object) -> None:
        """Raise ToolError on an unknown tool or invalid arguments, without echoing their values."""
        if not isinstance(name, str) or name not in self._tools:
            raise ToolError(f"Unknown tool {name!r}.")
        spec, _ = self._tools[name]
        if not isinstance(arguments, dict):
            raise ToolError(f"Arguments for {name!r} must be a JSON object.")
        # Resolve tool schemas locally, including schemas supplied by external tool servers.
        validator = validator_for(spec.parameters)(spec.parameters, registry=Registry())
        try:
            error = next(validator.iter_errors(arguments), None)
        except Unresolvable:
            raise ToolError(f"Unresolved schema reference for {name!r}.") from None
        if error is not None:
            field = ".".join(str(part) for part in error.absolute_path) or "arguments"
            raise ToolError(f"Invalid {field} for {name!r} ({error.validator}).")

    def execute(self, action: dict) -> dict:
        """Dispatch a named action or legacy Bash action; return expected tool failures as observations."""
        name = action.get("tool", "bash")
        arguments = action.get("arguments") if "tool" in action else {"command": action.get("command")}
        try:
            self.validate(name, arguments)
            return self._tools[name][1](arguments)
        except ToolError as error:
            return {"output": "", "returncode": 1, "exception_info": str(error)}


def make_tool_registry(environment: Environment) -> ToolRegistry:
    """Start a registry with Bash routed to the current execution environment."""
    registry = ToolRegistry()
    registry.register(ToolSpec("bash", "Execute a bash command", BASH_PARAMETERS), environment.execute)
    return registry
