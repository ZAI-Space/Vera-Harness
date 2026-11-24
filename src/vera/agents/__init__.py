"""Agent implementations for VERA."""

import copy
import importlib

from vera import Agent, Environment, Model
from vera.tools import ToolRegistry

_AGENT_MAPPING = {
    "default": "vera.agents.default.DefaultAgent",
    "interactive": "vera.agents.interactive.InteractiveAgent",
    "stateful": "vera.agents.stateful.StatefulAgent",
    "stateful_interactive": "vera.agents.stateful.StatefulInteractiveAgent",
    "hindsight": "vera.agents.hindsight.HindsightAgent",
    "hindsight_interactive": "vera.agents.hindsight.HindsightInteractiveAgent",
}


def get_agent_class(spec: str) -> type[Agent]:
    """Resolve a short name or dotted import path to an agent class.

    Unknown names raise ``ValueError``. Import and attribute errors are reported
    as the same configuration error; constructor errors propagate unchanged.
    """
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
    """Construct an agent from a copied configuration and existing adapters.

    ``agent_class`` in ``config`` takes precedence over ``default_type``. The
    factory does not create model or environment resources. A supplied registry
    is passed to the agent; configuration and construction errors propagate.
    """
    config = copy.deepcopy(config)
    agent_class = get_agent_class(config.pop("agent_class", default_type))
    if tool_registry is not None:
        return agent_class(model, env, tool_registry=tool_registry, **config)
    return agent_class(model, env, **config)
