"""Test a configured MCP endpoint without enabling it or executing its tools."""

import time

from vera.tools import ToolError, ToolRegistry
from vera.tools.mcp import open_mcp_tools, parse_mcp_servers


def probe_server(name: str, config: dict) -> dict:
    """Initialize and list tools, then close the transport; return a dated result.

    A stdio test starts the explicitly configured process. No tool is called and
    no credential values are returned. Session runtimes open their own clients.
    """
    registry = ToolRegistry()
    try:
        with open_mcp_tools(registry, parse_mcp_servers({name: config})):
            tools = [
                {"name": row["function"]["name"], "displayName": row["function"]["name"].removeprefix(f"mcp_{name}_")}
                for row in registry.definitions()
            ]
        return {"ok": True, "checkedAt": int(time.time() * 1000), "tools": tools}
    except ToolError as error:
        return {"ok": False, "checkedAt": int(time.time() * 1000), "tools": [], "error": str(error)}
