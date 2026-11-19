[English](subagents.md) · [简体中文](zh/subagents.md)

# Subagents

Define roles in a YAML overlay, then give the main agent a task. A role describes when to delegate, how the child should behave and which tools and skills it can access.

```yaml
subagents:
  max_runs: 8
  roles:
    documentation-reviewer:
      description: Check public documentation against the implementation.
      instructions: |
        Inspect the named module and cite concrete lines in your findings.
        Limit the review to the assigned files.
      model:
        model_class: litellm
        model_name: openai/gpt-4o-mini
      tools: [bash]
      skills: []
      step_limit: 12
      cost_limit: 0.5
      wall_time_limit_seconds: 180
```

```bash
vera -c vera.yaml -c roles.yaml -t "Ask the documentation-reviewer to review the command-line examples"
```

Use any tool-calling model adapter supported by `vera`. Omit `model` to construct a fresh instance of the parent's model configuration. A role that sets `model` supplies its own complete model config. Set `skills` to names from the [local skill catalog](skills.md). Each role sees only its own configured skills. `tools` accepts registered names, including web or MCP tools configured in the parent run. Bash gives the role the runtime's normal shell access, including writes.

The parent discovers roles with `subagents_list` and invokes `subagent_run` with a role name and a self-contained task. The call waits for the result. Each child starts with its role instructions and task, and shares the parent's environment and already-open tool connections. Interactive authorization uses the parent's current mode. The main agent receives a summary, status, turn and cost counts, and a trajectory path when trajectory output is enabled.

The run limit applies to the number of delegations in one CLI session. Child cost counts toward the parent's budget. Step, cost, and wall-time limits are checked between model calls, as in the main agent. Children use `subagent_finish` to return a summary. Delegation tools are available to the main agent.
