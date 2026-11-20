[English](python_bindings.md) · [简体中文](../zh/usage/python_bindings.md)

# Python bindings

!!! abstract "Reuse the shared Runtime"

    Use `open_agent_runtime` when a caller needs the same plugins, MCP, Skills, Subagents and sandbox policies as the terminal. The context owns connections and must remain open for the run.

```python
from vera.config import get_config_from_spec
from vera.runtime import open_agent_runtime

config = get_config_from_spec("vera.yaml")
config["model"] = {"model_class": "litellm", "model_name": "openai/YOUR_MODEL"}
with open_agent_runtime(config) as runtime:
    result = runtime.agent.run("Inspect the project and report findings")
```

For a noninteractive caller, choose an appropriate agent config and explicit permissions; an interactive confirmation prompt needs a human input adapter. For observation select `stateful` or `stateful_interactive`. Default templates come from the built-in YAML: constructing `DefaultAgent` without `system_template` and `instance_template` is not a complete example.

The implementation now lives in the `vera` namespace. Update inherited `minisweagent.*` imports and custom class paths to `vera.*`; compatibility aliases cover CLI names, not old Python modules. See [subclassing](../advanced/cookbook.md), [state](../agent-state.md), and [frontend boundaries](../frontend-integration.md).
