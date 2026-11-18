"""Agent implementations for mini-SWE-agent."""

import copy
import importlib

from minisweagent import Agent, Environment, Model
from minisweagent.tools import ToolRegistry

_AGENT_MAPPING = {
    "default": "minisweagent.agents.default.DefaultAgent",
    "interactive": "minisweagent.agents.interactive.InteractiveAgent",
    "stateful": "minisweagent.agents.stateful.StatefulAgent",
    "stateful_interactive": "minisweagent.agents.stateful.StatefulInteractiveAgent",
    "hindsight": "minisweagent.agents.hindsight.HindsightAgent",
    "hindsight_interactive": "minisweagent.agents.hindsight.HindsightInteractiveAgent",
}


def get_agent_class(spec: str) -> type[Agent]:
    full_path = _AGENT_MAPPING.get(spec, spec)
    try:
        module_name, class_name = full_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except (ValueError, ImportError, AttributeError):
        msg = f"Unknown agent type: {spec} (resolved to {full_path}, available: {_AGENT_MAPPING})"
        raise ValueError(msg)


def get_agent(
    model: Model, env: Environment, config: dict, *, default_type: str = "", tool_registry: ToolRegistry | None = None
) -> Agent:
    config = copy.deepcopy(config)
    agent_class = get_agent_class(config.pop("agent_class", default_type))
    if tool_registry is not None:
        return agent_class(model, env, tool_registry=tool_registry, **config)
    return agent_class(model, env, **config)
