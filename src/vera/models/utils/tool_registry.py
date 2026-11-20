"""Share tool declarations and action parsing across function-calling providers."""

from vera.tools import BASH_PARAMETERS, ToolError, ToolRegistry

_BASH_FUNCTION = {"name": "bash", "description": "Execute a bash command", "parameters": BASH_PARAMETERS}
BASH_CHAT_TOOL = {"type": "function", "function": _BASH_FUNCTION}
BASH_RESPONSES_TOOL = {"type": "function", **_BASH_FUNCTION}


class ToolCallingModel:
    """Optional registry binding with a legacy Bash-only default."""

    tool_registry: ToolRegistry | None = None
    supports_tool_registry = True

    def bind_tool_registry(self, registry: ToolRegistry) -> None:
        """Use the same registry for model declarations and parsing."""
        if not self.supports_tool_registry:
            raise ToolError(
                "This model adapter uses text actions. Select a tool-calling model adapter for registered tools."
            )
        if self.tool_registry is not None and self.tool_registry is not registry:
            raise ToolError("Use a separate model adapter instance for each tool registry.")
        if "tools" in getattr(self.config, "model_kwargs", {}):
            raise ToolError("Remove model_kwargs.tools when using a tool registry.")
        self.tool_registry = registry

    def tool_definitions(self, *, responses: bool = False) -> list[dict]:
        """Return declarations formatted for the model's API."""
        if self.tool_registry is not None:
            return self.tool_registry.definitions(responses=responses)
        return [BASH_RESPONSES_TOOL if responses else BASH_CHAT_TOOL]


def parse_action(name: str, arguments: object, call_id: str, registry: ToolRegistry | None) -> dict:
    """Validate one action, retaining the original shape for Bash calls."""
    if registry is not None:
        registry.validate(name, arguments)
    elif name != "bash":
        raise ToolError(f"Unknown tool {name!r}.")
    if name == "bash":
        if not isinstance(arguments, dict) or "command" not in arguments:
            raise ToolError("Missing 'command' argument in bash tool call.")
        return {"command": arguments["command"], "tool_call_id": call_id}
    return {"tool": name, "arguments": arguments, "tool_call_id": call_id}
