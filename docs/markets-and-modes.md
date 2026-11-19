[English](markets-and-modes.md) · [简体中文](zh/markets-and-modes.md)

# Capability markets and explicit run modes

The market flow follows Hermes' separation between discovery, inspection and installation. The default MCP source is the [official MCP Registry](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/api/official-registry-api.md); the default Skill source is [skills.sh](https://github.com/vercel-labs/skills). Plugin marketplace sources remain GitHub and Gitee.

Search never starts a service or executes downloaded code. Inspect the publisher, pinned version, transport, required input and environment-variable names before adding an MCP service. Added services remain inactive until explicitly selected. Skills are fetched from their underlying GitHub repository as a fixed commit, validated using the existing Skill loader, and copied without executing installation scripts.

`/mcp` and `/skill` select installed capabilities for the next task. Market discovery and installation are settings operations, independent of model calls. The Python market interfaces are also intended for the desktop's settings UI.

```bash
vera-extra mcp search context7
vera-extra mcp inspect io.github.upstash/context7
vera-extra mcp add io.github.upstash/context7
vera-extra mcp list
vera-extra mcp remove context7
vera-extra skills search find-skills
vera-extra skills inspect vercel-labs/skills/find-skills
vera-extra skills install vercel-labs/skills/find-skills --ref COMMIT_SHA
vera-extra skills remove find-skills
```

The terminal accepts `/mcp search QUERY`, `/mcp add IDENTIFIER`, `/skill search QUERY`, and `/skill add OWNER/REPO/SKILL`. Afterwards `/mcp NAME` or `/skill NAME` selects it. Tab completion only reads local catalogs; it never performs a network search. The CLI's `inspect` previews transport/instructions before addition. MCP entries needing arguments accept `--input NAME=VALUE`; API headers accept `--header-env HEADER=ENV_NAME`. `--version` pins the selected MCP publisher record. Unsupported custom transports/runtime templates require manual configuration rather than guessing commands.

MCP saved settings default to `mcp-services` under VERA's global config directory; a host may choose `mcp_services.directory`. Existing `mcp_servers` entries take precedence. Settings alone never activate a saved service: set `mcp_selection` explicitly or choose `/mcp`. npm/PyPI stdio entries require Node.js/npx or uv/uvx, respectively, and resolve/download the pinned package when first started. Adding settings does not install these prerequisites. HTTP bearer and custom API headers reference environment variables, require HTTPS for remote services, and cannot override protocol headers. OAuth login and MCP bundle/OCI transports are not implemented by this market adapter.

Skills install in VERA's existing user skill directory, so existing discovery, selection and runtime skill tools can use them immediately. Removal only accepts unchanged market-owned snapshots. Modified local skills are preserved. Market records and downloaded instructions are publisher content, not trusted host instructions.

## Run modes

Run mode and permissions are separate. Choosing a goal does not grant `yolo`; the configured `confirm`, `yolo` or `human` mode still controls execution. Sandbox selection is independent of both.

Hermes' [`/plan`](https://github.com/NousResearch/hermes-agent/blob/fe8b920cae0980cef854f478236f525aaf2b93ce/agent/plan_prompt.py) requests a saved Markdown plan for one turn. VERA's plan tools inspect project files and save the final plan under `.vera/plans/`. Planning does not implement the task or invoke shell/MCP mutations. The plan should explain the goal, relevant files, implementation steps, exact validation commands, risks and open questions.

Hermes' [`/goal`](https://github.com/NousResearch/hermes-agent/blob/fe8b920cae0980cef854f478236f525aaf2b93ce/website/docs/user-guide/features/goals.md) keeps a standing objective, judges progress at turn boundaries, and continues within a finite budget. VERA uses the same pattern outside the existing Agent Loop. Goals have explicit status, pause/resume/clear controls, a persisted conversation, and bounded turns, cost and duration. Judge failure cannot be treated as completion. A blocked goal waits for user intervention.

Plan mode applies to one submitted task. Goal mode continues until completion, blocking, user pause/cancellation or a budget limit. Opening a plan while a goal is active pauses that goal; it does not authorize implementation after the plan is written.

```text
/plan Add streaming responses to this project
/goal Implement streaming responses and verify the regression tests pass
/goal status
/goal pause
/goal resume
/goal clear
```

`/goal -- TEXT` escapes a control word at the beginning of an objective. `/plan` without a request uses the last submitted task; without prior context it asks for an explicit request. Ordinary subsequent tasks leave plan/goal mode. `/stop` pauses an active goal and cancels the current task. During execution, pause applies at the next turn boundary; cancellation/confirmation use the existing agent controls. Switching to planning inside an approval prompt stops the old task before assembling the restricted planning runtime. Human mode requires selecting confirm/yolo before either model-driven mode.

Use `vera -t '/plan REQUEST' --exit-immediately` or `vera -t '/goal OBJECTIVE' --exit-immediately` for the same modes from the command line. Native tool-calling model adapters are required. Both model execution and the goal judge incur provider costs; HTTP protocol tests with local peers are not a paid provider acceptance test.

Goal configuration is host-owned:

```yaml
terminal:
  session_id: project-chat-1
goal:
  max_turns: 20
  cost_limit: 3
  timeout: 1800
  # Optional complete model configuration for a separate judge:
  # judge_model: {model_class: litellm, model_name: openai/your-judge}
```

Goals persist under the user config directory, keyed by the resolved workspace and `terminal.session_id` (default `default`). Desktop clients should assign a different ID per chat. Status reports objective, used turns, cost, elapsed time and stop reason; it omits the private conversation. Resume retains context and resets the per-resume budget. Changing runtime choices requires a new goal. A crash/interrupted turn must be inspected before setting a new goal; it is never automatically replayed.

The outer controller calls the unchanged agent run method, carries complete prior conversation into the next model request, and judges each submitted turn using its result and recent tool evidence. Judge output is constrained to done/continue/blocked. Invalid output or provider failure stops continuation; budget exhaustion pauses without claiming success. Model judges provide advisory evidence assessment, not guaranteed correctness. Cost and elapsed limits are checked at call/turn boundaries; an already in-flight provider call can exceed its remaining allowance.

Frontend adapters can use `TerminalSession.process`, `runtime_config`, `GoalStore.status/control` and `drive_goal`. `drive_goal` accepts a host-owned `run_turn(task, history, remaining)` callback; the caller retains runtime lifecycle, task storage, model configuration and permission prompting. No OS background service, automatic process wakeup or HTTP API is implied by goal mode.
