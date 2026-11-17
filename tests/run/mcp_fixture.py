"""FastMCP server available to the stdio subprocess and the HTTP integration test."""

import os

from mcp.server.fastmcp import FastMCP


def echo(text: str) -> dict[str, str | bool]:
    """Echo the text and indicate which test environment variables were forwarded."""
    return {
        "text": text,
        "allowed": "MCP_TEST_ALLOWED" in os.environ,
        "private": "MCP_TEST_PRIVATE" in os.environ,
    }


def fail() -> str:
    """Return a tool execution error over MCP."""
    raise ValueError("fixture refused")


def make_server() -> FastMCP:
    """Build an independent server for each transport session under test."""
    server = FastMCP("integration", json_response=True)
    server.add_tool(echo)
    server.add_tool(fail)
    return server


if __name__ == "__main__":
    make_server().run(transport="stdio")
