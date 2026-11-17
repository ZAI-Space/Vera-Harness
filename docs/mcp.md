# MCP tools

The `mini` CLI can load tools from MCP servers alongside Bash and web tools. Install the optional MCP client in the environment that runs `mini`.

```bash
python -m pip install -e ".[mcp]"
```

Create `mcp.yaml` with one entry per server. The following example assumes `local_server.py` already runs a stdio MCP server and the remote endpoint exposes `read_document`.

```yaml
mcp_servers:
  local:
    command: python
    args: [local_server.py]
    allow_tools: [echo]
  docs:
    url: https://mcp.example.com/mcp
    bearer_token_env: DOCS_MCP_TOKEN
    allow_tools: [read_document]
    timeout: 30
```

```bash
mini -c mini.yaml -c mcp.yaml
```

Use the same launch command in PowerShell, Git Bash and Linux once `mini` is on the active environment's PATH. For a local server, `command` points to an executable and `args` lists its arguments. On Windows you can set `command` to the full path to the server's `python.exe`. Set `cwd` to choose the server's working directory. Add environment variable names to `env_from` when the server needs credentials or other settings beyond the SDK's default environment. Define those variables before starting `mini`. Keep credential values out of the YAML and CLI arguments.

Tools normally appear as `mcp_<server>_<tool>`, for example `mcp_docs_read_document`. Omit `allow_tools` to expose all tools discovered on that server. Use an empty list to expose none. A misspelled name in the list causes startup to fail. Interactive confirmation applies to MCP calls in confirm mode. Local servers run as child processes with the CLI user's permissions. The agent sends its tool arguments to the configured server.

`mini` discovers tools at startup and closes connections when the run ends. The timeout is in seconds and applies to MCP requests and discovery. Protocol errors and tool failures appear in tool observations. Structured results are rendered as JSON, text results are shown as text, and other content types are represented by placeholders. Output is limited to 6,000 characters plus a truncation marker. This release supports stdio and Streamable HTTP with optional bearer authentication.
