[English](cookbook.md) · [简体中文](../zh/advanced/cookbook.md)

# Cookbook

!!! abstract "Compose first, subclass when necessary"

    Choose an Agent, Model and Environment, then assemble them in a run script. Use [shared Runtime](../usage/python_bindings.md) for the same integrated capabilities as the terminal. This avoids rewriting the Agent Loop for each extension.

## A complete base-agent example

```python
from vera.agents.default import DefaultAgent
from vera.config import get_config_from_spec
from vera.environments.local import LocalEnvironment
from vera.models import get_model

config = get_config_from_spec("default.yaml")
agent = DefaultAgent(
    get_model(config={"model_name": "openai/YOUR_MODEL", "model_class": "litellm"}),
    LocalEnvironment(cwd="."),
    **config["agent"],
)
result = agent.run("Inspect the project")
```

The built-in configuration supplies required templates. Substituting `InteractiveAgent` additionally requires interactive input/mode settings. Optional Docker/service environments require their own configuration and resources; constructing a class does not provision them.

## Register a named capability

```python
from vera.tools import ToolSpec, make_tool_registry

registry = make_tool_registry(agent.env)
registry.register(
    ToolSpec("lookup_status", "Read local application status", {"type": "object"}),
    lambda arguments: {"output": "ready", "returncode": 0, "exception_info": ""},
)
agent.tool_registry = registry
agent.model.bind_tool_registry(registry)
```

Use native tool calling and a separate model adapter instance per registry. Schemas and dispatch use the same registry. Prefer this mechanism over parsing a Python function name from Bash. MCP, web providers and plugins reuse it. Registered handlers must return the normal observation fields or deliberately raise a flow-control exception.

## Observe without changing control flow

Use `StatefulAgent`/`StatefulInteractiveAgent` and `subscribe` for UI state. Listeners receive copies and must not advance/mutate the agent. Add a [Subagent role](../subagents.md) for independent delegated context, or [Skill](../skills.md) for instructions. Neither requires patching `DefaultAgent.run`.

## Custom components

Implement the Protocol methods in `vera`: Model query/message formatting, Environment execution, and serialization/template variables. Factory configuration accepts full component class paths. `VERA_DEFAULT_RUN` still selects a custom Python entry. Keep orchestration at the caller boundary; `/goal` and scheduled workers illustrate external controllers. Use RunStore tracking for side-effect receipts and keep unknown results explicit.
