[English](cli.md) · [简体中文](../zh/usage/cli.md)

# `vera`

!!! abstract "Interactive terminal"

    `vera` starts the terminal. `python -m vera` uses the same command. Existing `vera` and `python -m vera` entries remain aliases. Run it in the project whose files you want to attach.

## Command line options

| Option | Purpose |
| --- | --- |
| `-t`, `--task` | Submit a task directly; otherwise prompt |
| `-m`, `--model` | Select a provider model |
| `--model-class`, `--agent-class` | Select an existing adapter or Python class path |
| `-c`, `--config` | Merge config specs in order; include `vera.yaml` when using overlays |
| `-y`, `--yolo` | Disable per-operation approval |
| `-l`, `--cost-limit` | Per-run cost limit; zero disables this limit |
| `--sandbox`, `--sandbox-profile` | Select a backend or saved profile; mutually exclusive |
| `--skill` | Inject one selected Skill |
| `--storage`, `--resume`, `--reconcile` | Persist and continue a recorded run |
| `-o`, `--output` | Trajectory path |
| `--exit-immediately` | Finish without asking for another task |

Use `vera --help` as the current option reference. A launcher's working directory and quoted arguments are preserved.

## Input and task selection

```text
Explain @src/main.py
/permissions confirm
/skill
/mcp
/plugin
/subagent
/sandbox
/plan Design a change before implementing it
/goal Complete the change and verify it
```

The [terminal guide](../terminal.md) describes completion, files and selections. `/plan` and `/goal` are explicit run modes, described in [markets and run modes](../markets-and-modes.md).

## Permission modes

`confirm` asks before proposed actions; `yolo` runs without per-action approval; `human` dispatches commands entered by the user. `/c`, `/y`, `/u` retain their existing prompt controls. A mode change is not a sandbox change. Ordinary tasks default to confirmation.

## Artifacts and integration

The terminal prints the configuration and trajectory paths. Enable [RunStore](../storage.md) for durable receipts. State and frontend adapters use [shared Runtime interfaces](../frontend-integration.md), rather than parsing colored terminal text.

::: vera.run.cli
