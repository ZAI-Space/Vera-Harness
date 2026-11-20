[English](yaml_configuration.md) · [简体中文](../zh/advanced/yaml_configuration.md)

# YAML configuration

!!! abstract "Merge explicit overlays onto a complete base"

    `-c` accepts a built-in config name, a file path or `section.key=value`. Specs merge from left to right. Supplying `-c` replaces the implicit default config list; include `vera.yaml` to retain required templates and normal terminal settings.

```bash
vera -c vera.yaml -c project.yaml -c agent.step_limit=40
```

```yaml
agent:
  agent_class: stateful_interactive
  mode: confirm
  step_limit: 40
  cost_limit: 1.0
  wall_time_limit_seconds: 300
model:
  model_class: litellm
  model_name: openai/YOUR_MODEL
environment:
  environment_class: local
  cwd: .
storage:
  path: ./runs.sqlite3
```

Use actual provider credentials in the environment, not this file. Keep artifact and private stores outside a writable project when they need protection from project tools.

## Component settings

| Section | Responsibility |
| --- | --- |
| `agent` | Class, templates, interactive mode, step/cost/time limits |
| `model` | Provider adapter, name, request options and accounting |
| `environment` | Low-level execution backend and cwd |
| `sandbox` / `sandbox_profile` | Isolation policy or named saved profile |
| `web`, `mcp_servers`, `mcp_selection` | External capabilities and explicit selection |
| `skills`, `plugins`, `subagents` | Workflows, installed capability packages and roles |
| `storage`, `terminal`, `goal`, `scheduler` | Persistence, session settings and outer controllers |

The loader recognizes names in the built-in config hierarchy and `VERA_CONFIG_DIR`. JSON/YAML value parsing applies to key-value specs; quote values for your host shell. Relative paths follow the owning module's contract: terminal settings use the workspace, channels resolve from their config location, and daemon settings should use explicit absolute project/store paths.

## Templates and custom classes

Templates use Jinja variables from Agent, Model, Environment and task context. `system_template` and `instance_template` are required for direct base-agent construction. Do not interpolate untrusted context into a new template; pass it as task data. Factory selectors accept existing shortcuts or full Python class paths. Read the corresponding API Config class instead of assuming every component accepts every setting.

`confirm`, `yolo` and `human` remain permission modes. `run_mode: plan|goal` belongs to the mode/controller flow; use the terminal commands or documented host callbacks rather than assuming a raw run_mode flag drives autonomous continuation.
