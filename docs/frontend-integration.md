[English](frontend-integration.md) · [简体中文](zh/frontend-integration.md)

# Frontend integration

!!! abstract "One Runtime, two entry points"

    VERA includes an Electron + React desktop in `desktop/` and an independent Python desktop service. The terminal entry point remains available. Electron never imports the agent SDK or launches tools inside the renderer.

## Start the desktop

Use Python 3.12, Node.js 24 LTS and Bash (Git Bash on Windows). Install the Python environment and desktop dependencies first:

```bash
uv venv --python 3.12
uv pip install -e '.[full,channels]'
cd desktop
npm ci
cd ..
```

Windows PowerShell: `powershell -File scripts/start-desktop.ps1`. Git Bash: `bash scripts/start-desktop.sh`. Linux/macOS Bash: `bash scripts/start-desktop.sh`. On Windows, the Bash wrapper uses the PowerShell lifecycle owner. An existing backend config can be supplied with `-Config path.yaml` on Windows or `--config path.yaml` on Unix. Configure and select a model in the desktop before an agent task; `human` can execute a manually entered Bash command without a model.

The launcher owns only its new service process and children. It creates an authenticated loopback connection file, builds the desktop and removes the connection file on exit. It never installs Docker or Bubblewrap.

## Integration map

| UI operation | Request / returned fields | Python boundary |
| --- | --- | --- |
| New conversation | `createSession({options:{cwd,provider?,modelId?,thinkingLevel?}})` → `SessionMeta` | `DesktopStore` |
| History and reconnect | `getSessionBaseline({sessionId})` → `meta,sequence,hydrationToken,transcript,permissionMode` | `Sessions`, SQLite |
| Send / stop | `prompt({sessionId,text,document?,images?})`, `abort({sessionId})` | Isolated worker + `open_agent_runtime` |
| Approve | `requestId,answer` with optional matching `sessionId` → resolution event | Scoped worker stdin; allow once / deny |
| File attachment | `listProjectFiles({cwd})` → relative paths; composer `file.path` parts | `ProjectFiles` |
| Model settings | Provider ID, protocol, base URL and definitions; execution pickers expose authenticated, visible models only | `Providers`, private credential vault |
| Role editor | Name, instructions, model reference, tools, skills and budgets | `SubagentConfig`, shared Runtime |
| Skill / MCP markets | Explicit search, preview and install/add; MCP saved disabled | `SkillMarket`, `MCPRegistry` |
| MCP settings | User scope, stdio or URL, direct exposure, enabled flag and explicit connection test | Python MCP SDK; tests initialize and list tools only |
| Plugins | GitHub / Gitee market, install, enable, disable, remove | `PluginManager` |
| Sandbox | Saved profile + availability/reason; unavailable choices disabled | `SandboxProfiles` |
| Schedule | Cadence, project, model, timezone → task/run snapshot | `JobStore`, independent scheduler service |
| Plan / goal | `/plan`, `/goal`, mode selection | Existing plan/goal module; no loop replacement |
| Export / fork / recall | Display history and retained pre-turn model context | SQLite + immutable runtime receipts |

Full TypeScript definitions live in `desktop/src/contracts/`; Python routing lives in `src/vera/desktop/`. UI preferences remain in Electron's user-data directory. Backend configuration, sessions, safe display exports, credential vault and run receipts live under the private VERA desktop state directory.

## Transport and streaming

The service binds only `127.0.0.1`. `/health`, `/invoke` and `/events?after=<cursor>` require a bearer token; cross-origin browser requests are rejected. The token stays in Electron's main process. Each reply is `{result: ...}`; failures carry an error and never imply success.

Long polling wakes when an event arrives. Provider SSE fragments are forwarded as `thinking_delta`, `text_delta` and tool-argument updates before response completion. Tool boundaries and `turn_end` preserve order. The original model parser validates the completed response before any tool executes. Read [streaming presentation](desktop-streaming.md) for the PI-Desktop source study and behavior.

Event envelopes carry `sessionId,sequence,event`. A cursor gap or service restart triggers rehydration; side-effect requests are never replayed automatically. Cancellation kills the owned worker tree, preserves received display text and clears pending approvals. Active sessions have independent workers and model contexts. One follow-up can wait behind an active task.

## Permissions and limits

`confirm` requests approval, `yolo` executes without individual approval, and `human` executes the command entered by the user. Approval currently offers allow once / deny; persistent command-whitelist editing is not exposed. Sandboxes are separate user-configured isolation environments. No available backend means disabled sandbox choices, not automatic installation.

The UI consistently labels these policies Human, Confirm and Yolo. Existing sessions persist their choice in the backend and restore it when reopened; new sessions inherit behavior defaults. Provider catalogs are separate from execution pickers: unconfigured, hidden and deleted models are excluded from those pickers. User Skills are available without first creating a conversation; enabled plugin Skills also appear in the resource catalog.

Test connection starts the configured MCP stdio process or connects to its URL, lists tools and closes the transport. It neither calls tools nor enables the service. Its dated result is a check, not a persistent connection. Arguments accept a JSON string array; Windows paths containing spaces belong in a single array item. Editing configuration invalidates the previous check.

Unattended schedules require explicit `yolo` and a fresh context per run. Saving leaves a task paused; manual tasks use Run now. Schedule times include the desktop's timezone; Monday-based UI weekdays are converted to cron weekdays. The scheduler has its own lifetime, so closing the desktop does not stop enabled schedules.

OAuth subscription login, SSH, LAN remote control, PI extensions, codemode/deferred MCP exposure and manual context compaction are not supplied by this backend adapter. Their UI entries are disabled or reject unsupported operations explicitly. MCP configuration applies to the next task; the settings page does not pretend a persistent connection is alive. These limits are separate from the existing Hindsight memory/context module.

## Verification

After installing dependencies and building, run `npm run test:ui` from `desktop/`. This launches actual Electron, Python service and local model protocol processes under a private temporary directory, clicks settings and sends commands, and checks the UI, SQLite and file effects. Windows remain hidden; no user configuration or paid model is used. The printed `EVIDENCE` directory retains reports, failure screenshots and logs. External-model and marketplace-network acceptance remain separate evidence.

The repository includes real HTTP/process, streaming SSE, approval, abort, persistence and scheduler adapter tests. A TypeScript integration test consumes events produced by an actual Python worker and verifies the final renderer projection. Electron acceptance additionally checks actual display, tool approval, Bash output and collapsible reasoning with a local protocol peer. A separate live DeepSeek run through the desktop service and worker completed streaming, tool execution and file creation with `Submitted`; see [streaming evidence](desktop-streaming.md#acceptance-evidence). Other providers and marketplace availability require their own credentials/network acceptance.
