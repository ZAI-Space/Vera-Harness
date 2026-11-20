[English](scheduler.md) · [简体中文](zh/scheduler.md)

# Scheduled tasks

VERA's independent scheduler follows [Hermes' cron architecture](https://github.com/NousResearch/hermes-agent/blob/fe8b920cae0980cef854f478236f525aaf2b93ce/website/docs/developer-guide/cron-internals.md): persist definitions, claim each occurrence before starting, and run a fresh agent session with bounded resources. This is a separate module using VERA's shared Runtime; the agent loop is unchanged.

## Create and run

Install the updated project dependencies (`python -m pip install -e .`). Save a job definition as `daily-check.yaml`:

```yaml
name: Daily project check
prompt: Inspect this project and report which checks pass, with actual command output.
schedule: "0 9 * * *"
timezone: Asia/Shanghai
workspace: C:/path/to/project  # On Linux, use an absolute Linux path.
config:
  agent:
    mode: yolo
  model:
    model_class: litellm
    model_name: openai/your-model
    model_kwargs:
      api_base: https://your-provider.example/v1
timeout: 600
step_limit: 50
cost_limit: 1
```

Configure the provider's API key in the environment before starting the service. No real key belongs in the YAML or shell arguments. The daemon inherits that environment; restart it after changing credentials. Job definitions are private local configuration snapshots, not a credential vault.

The commands work in PowerShell, Git Bash and Linux shells:

```bash
vera-extra cron create daily-check.yaml
vera-extra cron start
vera-extra cron status
vera-extra cron list
vera-extra cron show JOB_ID
vera-extra cron pause JOB_ID
vera-extra cron resume JOB_ID
vera-extra cron update JOB_ID daily-check.yaml --revision 3
vera-extra cron run JOB_ID
vera-extra cron history --job JOB_ID
vera-extra cron cancel EXECUTION_ID
vera-extra cron remove JOB_ID
vera-extra cron stop
```

`start` launches a detached service. `serve` runs in the current terminal; `tick` dispatches due/queued work once and waits. Creation and manual `run` only enqueue; a service or `tick` must dispatch them. Manual runs do not consume the regular schedule or repeat count. Pause/remove cancel queued work but leave ongoing work running; use `cancel` to stop an execution. Removal retains its history. Updating replaces the definition and resets its schedule/repeat count; queued/running work retains its original snapshot. A completed one-shot needs an edit or explicit manual run, rather than resume.

The default state directory is `scheduler` under VERA's global config directory. Put `--state PATH` before any subcommand to select another store. Only one scheduler can own a given store. `--workers` allows 1–16 concurrent jobs (default 2); a single job never overlaps itself.

## Timing and unattended permissions

| Schedule | Meaning |
| --- | --- |
| `30m` | Once, thirty minutes after creation/update |
| `every 2h` | Recurring interval measured as elapsed time |
| `0 9 * * *` | Five-field Cron in the job's IANA timezone |
| `2027-01-01T09:00:00` | Once, at local time in the job's timezone |
| `2027-01-01T01:00:00Z` | Once, at an explicit UTC instant |

Cron uses calendar time and timezone/DST rules. State uses UTC. `repeat` optionally caps scheduled attempts. Failures consume an attempt; there is no automatic side-effect retry. `grace_seconds` defaults to 120. An expired one-shot is recorded as skipped. Recurring missed slots coalesce into one invocation (`catch_up: true`), or a skipped-range receipt (`catch_up: false`); the backlog is never replayed as a burst.

Background jobs require explicit `config.agent.mode: yolo`. `confirm` and `human` need interactive input and are rejected. This choice is independent of sandbox isolation. Supply `config.sandbox_profile` and, if needed, `config.sandbox_profiles.path` to select a saved sandbox; missing engines/images fail the execution without falling back to the host. Installation remains the user's choice.

`config` uses the same Runtime configuration for models, Hindsight memory, web tools, MCP servers, plugins and Subagent roles. `skills` selects skills to inject into the initial task. Project `@file` references use the existing attachment rules. Every occurrence has fresh messages; shared long-term memory follows the configured memory provider. The per-invocation timeout, step and cost limits also bound delegated work through the existing Runtime.

## Agent tool and frontend integration

Enable the optional management tool in a host configuration:

```yaml
scheduler:
  enabled: true
  directory: ~/.config/VERA/scheduler  # Or another explicit local path.
```

`cronjob_manage` exposes create/list/update/pause/resume/run/remove. It only manages the current project's jobs and inherits host-owned Runtime configuration. The model cannot choose arbitrary credentials, another workspace or elevated execution permissions. The tool never starts a daemon implicitly. Scheduled workers disable it, including delegated access, to prevent recursive scheduling.

Desktop adapters can call `JobStore.create/get/list/update/control/history/cancel`, and `service_status/start_service/stop_service`. `update(..., revision=N)` provides an optimistic edit guard. Public views omit Runtime secrets; `definition()` and `execution()` are internal only. `Scheduler.owned()/tick()/wait()` provide a host-controlled dispatch API. These are Python interfaces; no HTTP server is installed by this module.

Each execution has an ID, status, summary and RunStore trace ID. Files are under `artifacts/EXECUTION_ID/`: `trajectory.json`, `result.json`, `process.log` and process ownership metadata. The normal parent/Subagent RunStore records are in `runs.sqlite3` beside `jobs.sqlite3`. The service log is `service.log`.

## Recovery and boundaries

Claims, next-run advancement and execution snapshots are one SQLite transaction. OS ownership prevents duplicate controllers. On restart, recorded child processes are identified by PID plus creation identity before cleanup. An atomic result already produced by a worker is recovered. Unknown/corrupt-result interrupted work is recorded as interrupted and never automatically replayed; inspect side effects before manually running again. Exactly-once external side effects cannot be guaranteed across a crash.

The detached service survives closing the launching CLI. It does not install itself at system boot, wake a sleeping computer, or operate while the machine is off. Results are local files, RunStore records and CLI/API history; proactive Weixin/Feishu delivery is not part of this module.
