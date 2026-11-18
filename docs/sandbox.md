# Workspace sandbox

Choose a mode when you start a run.

| Mode | Requirements and behavior |
| --- | --- |
| `auto` | Probes Bubblewrap on Linux or WSL, then tries a local Linux Docker engine with the configured image already present. If neither is usable, the CLI explains the available choices. |
| `bubblewrap` | Linux or WSL with Bubblewrap and working user namespaces. Each command runs in fresh namespaces and mounts the configured workspace. |
| `docker` | A local Linux Docker engine or Docker Desktop running Linux containers. The default image is `python:3.12-slim`. Run `docker pull python:3.12-slim` once if the image is missing. |
| `local` | Runs as the current host user, with the host filesystem, environment and network permissions. On Windows it uses Git Bash. Choose this mode for projects you trust. |

```bash
mini --sandbox auto
mini --sandbox bubblewrap
mini --sandbox docker
mini --sandbox local
```

Existing setups without a sandbox configuration keep their current environment. Vera probes local tools when asked to isolate a run. It leaves installation and image pulls to the user.
Choose a trusted Linux image with Bash and any build tools your project needs.

Put recurring choices in a YAML overlay and launch with `mini -c mini.yaml -c sandbox.yaml`.

```yaml
sandbox:
  mode: auto
  workspace: .
  workspace_access: read-only
  timeout: 30
```

Both isolated modes mount the workspace at `/workspace`, provide a temporary directory, and block shell network access. The default access mode is `read-write`. Sandbox mode applies to Bash calls by the parent and its Subagents. Subagents also keep their individual tool allowlists. Docker additionally limits CPU, memory and process count, and tears down the entire container on command timeout. Start a new run after a Docker command times out.

Model requests use the CLI's host-side model client. Host stdio MCP servers, remote MCP servers and web providers require explicit opt-in in the isolated modes. They run outside the shell sandbox with their respective host or service permissions.

```yaml
sandbox:
  mode: docker
  host_mcp_servers: [local-docs]
  remote_mcp_servers: [approved-api]
  allow_web_tools: true
```

The names must match entries in `mcp_servers`. Only opt in to servers you trust and send them data appropriate for their scope.
