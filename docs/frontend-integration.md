[English](frontend-integration.md) · [简体中文](zh/frontend-integration.md)

# Frontend integration

!!! abstract "Share capabilities, keep transport explicit"

    The terminal and desktop can share the backend. Public Python interfaces exist; this revision does not supply a complete desktop HTTP/WebSocket server. Do not infer readiness from matching display names.

## Integration map

| Frontend operation | Existing Python boundary | Contract |
| --- | --- | --- |
| File search and attachments | `ProjectFiles.list/attach` | Workspace-relative, bounded UTF-8; no credentials or escaping paths |
| Slash selection | `TerminalSession.catalog/process/runtime_config` | Choices apply to the next assembled task |
| Create/run task | `open_agent_runtime` + `agent.run` | Caller owns input, lifecycle, cancellation and cleanup |
| State and progress | `StatefulAgent.subscribe/state` | Detached snapshots; observers must not mutate execution |
| History/recovery | `RunStore` | Durable receipts; unknown effects require reconciliation |
| Skill/MCP markets | `SkillMarket`, `MCPRegistry`, `MCPServices` | Explicit inspection/addition; saved MCP services need selection |
| Plugins | `PluginManager` | Install and enable are separate |
| Sandbox settings | `SandboxProfiles` | User-configured availability; disable unavailable choices |
| Standing goals | `GoalStore`, `drive_goal` | Unique `terminal.session_id` per chat; bounded continuation |
| Scheduled tasks | `JobStore`, `Scheduler` | Separate daemon ownership; local result history |

## Permissions and execution

Expose `confirm`, `yolo`, `human` as operation modes. `human` is manual command input, not full approval of model actions. Plan mode offers only project inspection and the confined plan writer. A goal retains the configured permission mode. Sandboxes are a separate selector: list saved profiles, check availability, show failure reasons, and never auto-install a backend from a chat selection.

## Adapter responsibilities

Transport messages need task/chat IDs, a stable event envelope, cancellation ownership and an approval request/reply contract. Run blocking agent work outside the renderer, marshal events to the transport thread, and close runtime contexts on completion/error. Give each chat a distinct session ID and each run a fresh artifact path. Do not parse the colored terminal transcript as an API.

Private configuration and tokens stay on the backend; return safe catalog metadata/status instead. Do not expose `JobStore.definition/execution` or raw config/tracebacks to an untrusted client. Validate workspace scope and backend availability again when starting. A tool's unknown outcome must remain unknown after reconnect; no automatic side-effect replay.

## Joint acceptance

Verify file selection, all three approval modes, prompt decisions, model/MCP/Skill/plugin selection, unavailable sandbox behavior, state updates, cancellation, stored history/reconciliation, plan output and goal controls through the real UI. Transport restart and concurrent chat isolation need their own tests. Backend unit/protocol coverage does not substitute for that future frontend acceptance.
