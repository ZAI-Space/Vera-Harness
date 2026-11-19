[English](sandbox.md) · [简体中文](zh/sandbox.md)

# Workspace sandbox

## Saved environments

Sandbox engines and images are installed/configured by the user. VERA never
downloads Docker, Bubblewrap or images, and does not register detected engines
as profiles automatically. Users without these tools can continue locally.

Create a configuration file, for example `python-sandbox.yaml`:

```yaml
mode: docker
docker_image: python:3.12-slim
workspace_access: read-write
timeout: 30
```

Register it independently of any model:

```bash
vera-extra sandboxes save python-dev python-sandbox.yaml
vera-extra sandboxes list
vera-extra sandboxes check --workspace .
vera-extra sandboxes save python-dev python-sandbox.yaml --replace
vera-extra sandboxes remove python-dev
```

The default store is `sandbox-profiles.sqlite3` under the global config directory.
`vera-extra sandboxes --store PATH ...` selects a different user-owned store;
configure `sandbox_profiles.path` to use that store from the runtime.
Named profiles require an explicit `docker` or `bubblewrap` backend, so their
identity never changes automatically. Each profile accepts existing SandboxConfig
fields. Changes are transactional and replacement requires explicit intent.

In the terminal, `/sandbox` returns fresh availability; `/sandbox python-dev`
selects an available profile for the next task. `/sandbox none` explicitly
selects local execution. `vera --sandbox-profile python-dev -t 'TASK'` selects
the same profile without the interactive prompt. A runtime config may also set
`sandbox_profile: python-dev`. Mixing that selection with `--sandbox` is rejected.

The current project directory is bound when selecting a profile in a terminal.
Direct runtime callers can supply their project through `sandbox.workspace` or
`environment.cwd`; otherwise the saved workspace is used. Profile options replace
the previous sandbox configuration completely. The parent and its Subagents
share the selected runtime and project boundary. Mid-task changes affect the next
task; already running environments keep their configuration.

Settings can save profiles even if the engine is offline. Availability checks
validate the project, backend and cached Docker image without starting containers;
Bubblewrap uses a bounded namespace probe. A failed startup reports an error and
never silently runs on the host.

### Backend interface for desktop integration

`SandboxProfiles.save/list_profiles/remove` manage settings. `check/status` probe
only saved profiles and provide `available`, `code` and `reason`. Reading an empty
store does not create a database or probe installed engines.

`TerminalSession.sandbox_status()` returns, for example:

```json
{
  "configured": false,
  "enabled": false,
  "reason": "Configure a sandbox in settings first.",
  "choices": [],
  "selected": null
}
```

Disable the picker when `enabled` is false. If profiles exist, show each choice
and disable those with `available: false`, displaying its reason. This is a
snapshot; call again to refresh after settings or engine changes.
`TerminalSession.select_sandbox(name)` validates before updating selection;
`select_sandbox(None)` chooses local explicitly. `set_mode("confirm"|"yolo"|"human")`
changes operation mode independently. `runtime_config()` produces a detached
configuration for the next task; these APIs require no frontend or HTTP transport.

## Existing backend selection

Choose a mode when you start a run.

| Mode | Requirements and behavior |
| --- | --- |
| `auto` | Probes Bubblewrap on Linux or WSL, then tries a local Linux Docker engine with the configured image already present. If neither is usable, the CLI explains the available choices. |
| `bubblewrap` | Linux or WSL with Bubblewrap and working user namespaces. Each command runs in fresh namespaces and mounts the configured workspace. |
| `docker` | A local Linux Docker engine or Docker Desktop running Linux containers. The default image is `python:3.12-slim`. Run `docker pull python:3.12-slim` once if the image is missing. |
| `local` | Runs as the current host user, with the host filesystem, environment and network permissions. On Windows it uses Git Bash. Choose this mode for projects you trust. |

```bash
vera --sandbox auto
vera --sandbox bubblewrap
vera --sandbox docker
vera --sandbox local
```

Existing setups without a sandbox configuration keep their current environment. VERA probes local tools when asked to isolate a run. It leaves installation and image pulls to the user.
Choose a trusted Linux image with Bash and any build tools your project needs.

Put recurring choices in a YAML overlay and launch with `vera -c vera.yaml -c sandbox.yaml`.

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
