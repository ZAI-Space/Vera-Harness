"""Connect configured MCP servers and register their tools for one agent run."""

import json
import os
import re
from collections.abc import AsyncIterator, Iterator
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager
from datetime import timedelta
from functools import partial
from hashlib import sha256
from importlib.util import find_spec
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlsplit

from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError, model_validator

from vera.tools import ToolError, ToolRegistry, ToolSpec

if TYPE_CHECKING:
    from anyio.from_thread import BlockingPortal
    from mcp import ClientSession
    from mcp.types import Tool


class MCPServerConfig(BaseModel):
    """Configure a stdio command or Streamable HTTP endpoint and its tool allowlist."""

    model_config = ConfigDict(extra="forbid")
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env_from: list[str] = Field(default_factory=list)
    optional_env_from: list[str] = Field(default_factory=list)
    url: str | None = None
    bearer_token_env: str | None = None
    headers_from: dict[str, str] = Field(default_factory=dict)
    allow_tools: list[str] | None = None
    timeout: float = Field(default=30, gt=0, le=300)

    @model_validator(mode="after")
    def validate_transport(self):
        """Require exactly one transport and reject settings for the other transport."""
        if bool(self.command) == bool(self.url):
            raise ValueError("Set exactly one of command and url.")
        variables = [*self.env_from, *self.optional_env_from, *self.headers_from.values()]
        if self.bearer_token_env is not None:
            variables.append(self.bearer_token_env)
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in variables):
            raise ValueError("Credential references must be valid environment variable names.")
        if self.command and (self.bearer_token_env is not None or self.headers_from):
            raise ValueError("HTTP credential settings require a url.")
        if any(
            not re.fullmatch(r"[A-Za-z0-9_-]+", name)
            or name.lower()
            in {"host", "content-type", "content-length", "accept", "mcp-session-id", "mcp-protocol-version"}
            for name in self.headers_from
        ):
            raise ValueError("Custom headers cannot override HTTP or MCP protocol headers.")
        if self.bearer_token_env and any(name.lower() == "authorization" for name in self.headers_from):
            raise ValueError("Choose one Authorization credential source.")
        if self.url:
            if self.args or self.cwd is not None or self.env_from or self.optional_env_from:
                raise ValueError("args, cwd and env_from require a command.")
            url = urlsplit(self.url)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or url.fragment:
                raise ValueError("url must be an HTTP(S) endpoint without credentials or a fragment.")
            if (
                (self.bearer_token_env or self.headers_from)
                and url.scheme != "https"
                and url.hostname not in {"127.0.0.1", "localhost", "::1"}
            ):
                raise ValueError("Bearer tokens require HTTPS for remote servers.")
        return self


ServerName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
_SERVER_CONFIGS = TypeAdapter(dict[ServerName, MCPServerConfig])


def parse_mcp_servers(config: object) -> dict[str, MCPServerConfig]:
    """Validate the MCP server mapping and report errors with their config paths."""
    try:
        return _SERVER_CONFIGS.validate_python(config)
    except ValidationError as error:
        issues = []
        for issue in error.errors(include_input=False):
            location = issue["loc"]
            field = ".".join(map(str, location)) if location and location[-1] != "[key]" else "server name"
            issues.append(f"{field}: {issue['msg']}")
        raise ToolError(f"Invalid mcp_servers config: {'; '.join(issues)}") from None


@asynccontextmanager
async def _open_session(config: MCPServerConfig) -> AsyncIterator["ClientSession"]:
    import httpx
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    async with AsyncExitStack() as stack:
        if config.command:
            transport = stdio_client(
                StdioServerParameters(
                    command=config.command,
                    args=config.args,
                    cwd=config.cwd,
                    env={
                        name: os.environ[name]
                        for name in [*config.env_from, *config.optional_env_from]
                        if name in os.environ
                    },
                )
            )
            read, write = await stack.enter_async_context(transport)
        else:
            headers = {name: os.environ[variable] for name, variable in config.headers_from.items()}
            if config.bearer_token_env:
                headers["Authorization"] = f"Bearer {os.environ[config.bearer_token_env]}"
            client = await stack.enter_async_context(
                httpx.AsyncClient(headers=headers, timeout=config.timeout, follow_redirects=False)
            )
            read, write, _ = await stack.enter_async_context(streamable_http_client(config.url, http_client=client))
        session = await stack.enter_async_context(
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=config.timeout))
        )
        await session.initialize()
        yield session


async def _discover(session: "ClientSession", allow_tools: list[str] | None, timeout: float) -> list["Tool"]:
    from anyio import fail_after

    tools = {}
    cursor = None
    seen_cursors = set()
    with fail_after(timeout):
        while True:
            page = await session.list_tools(cursor=cursor)
            for tool in page.tools:
                if tool.name in tools:
                    raise ToolError(f"Duplicate MCP tool {tool.name!r}.")
                tools[tool.name] = tool
            cursor = page.nextCursor
            if cursor is None:
                break
            if cursor in seen_cursors or len(seen_cursors) >= 100:
                raise ToolError("MCP tool discovery exceeded its pagination limit.")
            seen_cursors.add(cursor)
    if allow_tools is None:
        return list(tools.values())
    if missing := set(allow_tools) - tools.keys():
        raise ToolError(f"MCP tools not found: {', '.join(sorted(missing))}.")
    return [tool for name, tool in tools.items() if name in allow_tools]


def mcp_tool_name(server: str, tool: str) -> str:
    """Return the stable registry name used for a server/tool pair, including long-name hashing."""
    name = f"mcp_{server}_{tool}"
    normalized = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    if normalized == name and len(name) <= 64:
        return name
    return f"{normalized[:51]}_{sha256(name.encode()).hexdigest()[:12]}"


def _call_tool(portal: "BlockingPortal", session: "ClientSession", server: str, tool: str, arguments: dict) -> dict:
    try:
        result = portal.call(session.call_tool, tool, arguments)
    except Exception as error:
        return {
            "output": "",
            "returncode": 1,
            "exception_info": f"MCP tool {server!r}/{tool!r} failed ({type(error).__name__}).",
            "extra": {"result_unknown": True},
        }
    if result.structuredContent is not None and not result.isError:
        output = json.dumps(result.structuredContent, ensure_ascii=False)
    else:
        output = "\n".join(
            block.text if block.type == "text" else f"[MCP {block.type} omitted]" for block in result.content
        )
    if len(output) > 6000:
        output = output[:6000] + "\n[MCP output truncated]"
    return {
        "output": output,
        "returncode": int(result.isError),
        "exception_info": "MCP tool error" if result.isError else "",
    }


@contextmanager
def open_mcp_tools(registry: ToolRegistry, servers: dict[str, MCPServerConfig]) -> Iterator[None]:
    """Register MCP tools in a per-run registry. Calls require this context to stay open."""
    if not servers:
        yield
        return
    if find_spec("mcp") is None:
        raise ToolError('MCP is enabled. Install it with pip install "vera-harness[mcp]".')

    from anyio.from_thread import start_blocking_portal

    with ExitStack() as stack:
        portal = stack.enter_context(start_blocking_portal())
        for name, config in servers.items():
            for variable in (*config.env_from, *config.headers_from.values(), config.bearer_token_env):
                if variable is not None and variable not in os.environ:
                    raise ToolError(f"MCP server {name!r} requires the environment variable {variable!r}.")
            try:
                # Close in the same async task without forwarding agent errors into SDK task groups.
                context = portal.wrap_async_context_manager(_open_session(config))
                session = context.__enter__()
                stack.callback(context.__exit__, None, None, None)
                tools = portal.call(_discover, session, config.allow_tools, config.timeout)
            except ToolError as error:
                raise ToolError(f"MCP server {name!r}: {error}") from None
            except Exception as error:
                raise ToolError(f"MCP server {name!r} setup failed ({type(error).__name__}).") from None
            for tool in tools:
                spec = ToolSpec(mcp_tool_name(name, tool.name), tool.description or tool.name, tool.inputSchema)
                try:
                    registry.register(spec, partial(_call_tool, portal, session, name, tool.name))
                except SchemaError:
                    raise ToolError(f"MCP tool {name!r}/{tool.name!r} has an invalid input schema.") from None
        yield
