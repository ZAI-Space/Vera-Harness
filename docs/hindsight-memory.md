[English](hindsight-memory.md) · [简体中文](zh/hindsight-memory.md)

# Hindsight project memory

Use a running [Hindsight service](https://github.com/vectorize-io/hindsight) and
choose a memory bank for this project. For a local service, the default endpoint
is `http://127.0.0.1:8888`. Hindsight configures its own model separately from
the model the Harness uses. For Hindsight Cloud, create the bank in the console
and use `https://api.hindsight.vectorize.io` with a key scoped to that bank.

From Git Bash in the project directory:

```bash
export HINDSIGHT_BANK_ID=harness-project
export HINDSIGHT_BASE_URL=http://127.0.0.1:8888
./.venv/Scripts/vera-extra.exe memory retain 'Run local regression tests with pytest.'
./.venv/Scripts/vera-extra.exe memory recall 'How do I run regression tests?'
bash scripts/start.sh --agent-class hindsight_interactive
```

PowerShell uses `$env:HINDSIGHT_BANK_ID = 'harness-project'`,
`$env:HINDSIGHT_BASE_URL = 'http://127.0.0.1:8888'`, and
`./start.cmd --agent-class hindsight_interactive`. The `vera-extra` commands work
in PowerShell too. On Linux, use `.venv/bin/vera-extra`.

For authentication, set `HINDSIGHT_API_KEY_FILE` to the path of a file containing
only the key, or set `HINDSIGHT_API_KEY` in the process environment. Keep credential
files out of the checkout and use HTTPS for remote authenticated requests.

The interactive agent sends the initial task to each configured bank and adds
bounded reference notes to the initial user prompt. The prompt appears in the
trajectory and is sent to the Harness model. If a bank fails, the agent logs the
error and uses the available context. For noninteractive tasks, use
`--agent-class hindsight` with the corresponding agent configuration.

| Scope | Source | Configuration |
| --- | --- | --- |
| Current session | Agent messages and tool results | Remain in the complete trajectory. Set `agent.context_budget_chars` to compact older groups before each model query. |
| Project | Hindsight facts, experiences and consolidated observations | Set `HINDSIGHT_BANK_ID` or `agent.memory_bank_id`. Use a distinct bank and scoped key per project. |
| Shared across projects | A dedicated Hindsight bank containing reusable knowledge | Opt in with `agent.memory_shared_bank_id`. The same task query is sent to this bank, which the Agent reads and the operator curates. |
| Independently constructed Hindsight agents | A dedicated primary bank and optional shared bank | Python callers can construct Hindsight agents with separate `memory_bank_id`, `memory` and `shared_memory` clients. Built-in role delegation currently constructs `StatefulAgent` children and does not expose Hindsight bank configuration. |

For example, enable a shared bank and a soft 24,000-character model context budget:

```bash
bash scripts/start.sh --agent-class hindsight_interactive \
  -c vera.yaml -c agent.memory_shared_bank_id=harness-shared \
  -c agent.context_budget_chars=24000
```

Context compaction keeps the initial instructions, recent complete tool-call
groups and user steering. Older groups can be replaced with bounded excerpts.
The budget is measured in characters, and protected messages or large recent
tool results can exceed it. The full trajectory remains available for inspection.

### Resolving outdated or conflicting memories

The default recalls facts and observations with Hindsight's `prefer_observations`
enabled. When Hindsight returns a consolidated observation, it can omit raw
facts that directly contributed to it. The prompt preserves available fact IDs,
source IDs, dates, and bank identity. If sources disagree, the agent is prompted
to check the current workspace and report unresolved conflicts. Consolidation may
lag behind recent writes.

`reflect` uses Hindsight's synthesis over facts, observations and mental models
and can return supporting evidence. Select `agent.memory_mode=reflect` when a
task benefits from synthesis and you accept the extra model call at Hindsight.
The default remains observation-preferred recall. For the manual workflow:

```bash
./.venv/Scripts/vera-extra.exe memory retain 'The project switched to pnpm.' \
  --document-id package-manager-decision --context 'Verified against pnpm-lock.yaml'
./.venv/Scripts/vera-extra.exe memory recall 'Which package manager is current?' --json-output
./.venv/Scripts/vera-extra.exe memory reflect 'Which convention is current, and what supports it?' --json-output
./.venv/Scripts/vera-extra.exe memory invalidate FACT_ID 'Verified obsolete against the workspace'
./.venv/Scripts/vera-extra.exe memory restore FACT_ID
```

Retain accepts curated notes with optional source context, document ID and tags.
Use Hindsight's bank settings to define what it extracts and consolidates.
Automatic transcript ingestion and automatic fact retirement are outside this
workflow. These CLI commands use the bank in `HINDSIGHT_BANK_ID`.

### Comparing retrieval modes

Use the same model, task, workspace and bank snapshot, then vary only
`agent.memory_mode`: `disabled`, `facts`, `observations` or `reflect`. Keep the
context budget and shared-bank setting fixed. Example checks:

- The repository moved from npm to pnpm. Measure selection of the current command.
- Two equally credible facts disagree. Check for workspace verification or explicit uncertainty.
- The shared bank conflicts with a project decision. Check that current project evidence takes priority.
- A child's bank contains a note that its sibling must never retrieve. Check the returned bank and fact IDs.
- A long session spans several tool calls and a user correction. Check retained constraints, token usage and task success.

The local HTTP tests verify the request contracts and what the Agent receives.
They cannot measure Hindsight's factual consolidation or the model's task quality.
Use a running Hindsight service for that comparison.
