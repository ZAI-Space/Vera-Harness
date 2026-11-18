"""Start independent, bounded role runs against the parent agent's runtime."""

import json
import re
import time
from collections.abc import Callable
from contextlib import nullcontext
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from minisweagent.agents.default import DefaultAgent
from minisweagent.agents.interactive import InteractiveAgent
from minisweagent.agents.stateful import StatefulAgent
from minisweagent.exceptions import InterruptAgentFlow, Submitted
from minisweagent.models import get_model
from minisweagent.storage import StorageError
from minisweagent.tools import ToolError, ToolRegistry, ToolSpec
from minisweagent.tools.skills import Skill, register_skill_tools

_DELEGATION_TOOLS = {"subagents_list", "subagent_run", "subagent_finish"}
_SKILL_TOOLS = {"skills_list", "skill_view"}


class SubagentRole(BaseModel):
    """Declare the behavior, model and permissions of each new instance of a role."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    description: str = Field(min_length=1, max_length=320)
    instructions: str = Field(min_length=1, max_length=16_000)
    model: dict | None = None
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    step_limit: int = Field(default=12, ge=1, le=200)
    cost_limit: float = Field(default=0.5, gt=0)
    wall_time_limit_seconds: int = Field(default=180, ge=1, le=3600)

    @field_validator("model")
    @classmethod
    def check_model(cls, value: dict | None) -> dict | None:
        """Require a complete model selection when overriding the parent's adapter."""
        if value is not None:
            model_name = value.get("model_name")
            if not isinstance(model_name, str) or not model_name.strip():
                raise ValueError("A role model override requires model_name.")
        return value

    @field_validator("tools")
    @classmethod
    def check_tools(cls, value: list[str]) -> list[str]:
        """Keep orchestration and skill tools under the runtime's control."""
        if reserved := set(value) & (_DELEGATION_TOOLS | _SKILL_TOOLS):
            raise ValueError(f"Reserved tools: {', '.join(sorted(reserved))}. Configure skills in the skills field.")
        return value


class SubagentConfig(BaseModel):
    """Configure a run-local catalog of user-defined roles and a delegation limit."""

    model_config = ConfigDict(extra="forbid")
    roles: dict[str, SubagentRole] = Field(default_factory=dict)
    max_runs: int = Field(default=8, ge=1, le=64)

    @field_validator("roles")
    @classmethod
    def check_role_names(cls, roles: dict[str, SubagentRole]) -> dict[str, SubagentRole]:
        """Keep stable role identifiers for dispatch and bound the advertised catalog."""
        if len(roles) > 64 or any(not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name) for name in roles):
            raise ValueError(
                "Use up to 64 role names beginning with a lowercase letter and containing lowercase letters, digits or hyphens."
            )
        return roles


class _DelegatedAgent(StatefulAgent):
    def __init__(self, *args, authorize: Callable[[dict], None], **kwargs):
        super().__init__(*args, **kwargs)
        self._authorize = authorize

    def _execute_action(self, action: dict) -> dict:
        if action.get("tool") != "subagent_finish":
            self._authorize(action)
        return super()._execute_action(action)


def _finish(arguments: dict) -> dict:
    summary = arguments["summary"]
    raise Submitted({"role": "exit", "content": summary, "extra": {"exit_status": "Submitted", "submission": summary}})


def _observation(value: dict, *, status: int = 0) -> dict:
    return {"output": json.dumps(value, ensure_ascii=False), "returncode": status, "exception_info": ""}


def register_subagent_tools(
    registry: ToolRegistry,
    parent: DefaultAgent,
    config: SubagentConfig,
    parent_model_config: dict,
    skills: dict[str, Skill],
) -> None:
    """Attach role discovery and synchronous delegation for this parent run.

    A child gets a fresh model and context. Configured tools reuse registered handlers
    and any interactive authorization stays with the parent.
    """
    if not isinstance(parent, DefaultAgent):
        raise ToolError("Subagent delegation requires a DefaultAgent-compatible parent.")
    for name, role in config.roles.items():
        try:
            registry.select(role.tools)
        except ToolError as error:
            raise ToolError(f"Subagent role {name!r}: {error}") from None
        if missing := set(role.skills) - skills.keys():
            raise ToolError(f"Subagent role {name!r} uses unavailable skills: {', '.join(sorted(missing))}.")
    run_count = 0

    def authorize(action: dict) -> None:
        if isinstance(parent, InteractiveAgent):
            if parent.config.mode == "human":
                raise InterruptAgentFlow(
                    {
                        "role": "exit",
                        "content": "Delegation cancelled.",
                        "extra": {
                            "exit_status": "Cancelled",
                            "submission": "",
                        },
                    }
                )
            if "tool" in action:
                parent._ask_confirmation_or_interrupt([], tool_calls=[action])
            else:
                parent._ask_confirmation_or_interrupt([action["command"]])

    def list_roles(arguments: dict) -> dict:
        query = arguments.get("query", "").casefold()
        offset = int(arguments.get("offset", 0))
        roles = [
            {"role": name, "description": role.description}
            for name, role in sorted(config.roles.items())
            if query in name or query in role.description.casefold()
        ]
        end = offset + 12
        return _observation({"roles": roles[offset:end], "next_offset": end if end < len(roles) else None})

    def run_role(arguments: dict) -> dict:
        nonlocal run_count
        name = arguments["role"]
        if name not in config.roles:
            raise ToolError(f"Unknown subagent role {name!r}. Use subagents_list to find configured roles.")
        if run_count >= config.max_runs:
            raise ToolError("Subagent delegation limit reached for this run.")
        role = config.roles[name]
        cost_limit = role.cost_limit
        time_limit = role.wall_time_limit_seconds
        if parent.config.cost_limit > 0:
            cost_limit = min(cost_limit, parent.config.cost_limit - parent.cost)
        if parent.config.wall_time_limit_seconds > 0:
            remaining = parent.config.wall_time_limit_seconds - int(time.time() - parent._start_time)
            time_limit = min(time_limit, remaining)
        if cost_limit <= 0 or time_limit <= 0:
            raise ToolError("Parent budget exhausted before delegation.")
        child_registry = registry.select(role.tools)
        if role.skills:
            register_skill_tools(child_registry, {skill: skills[skill] for skill in role.skills})
        child_registry.register(
            ToolSpec(
                "subagent_finish",
                "Return the result of this delegated task.",
                {
                    "type": "object",
                    "properties": {"summary": {"type": "string", "minLength": 1, "maxLength": 3500}},
                    "required": ["summary"],
                    "additionalProperties": False,
                },
            ),
            _finish,
        )

        run_count += 1
        run_id = uuid4().hex
        parent_path = parent.config.output_path
        output = parent_path.parent / f"{parent_path.stem}.subagents" / f"{run_id}.traj.json" if parent_path else None
        child = None
        try:
            model = get_model(config=parent_model_config if role.model is None else role.model)
            child = _DelegatedAgent(
                model,
                parent.env,
                authorize=authorize,
                tool_registry=child_registry,
                system_template=(
                    "You are the {{ role_name }} subagent. Work on the delegated task below and return your result using "
                    "subagent_finish. Use skills_list and skill_view when relevant and available.\n\n{{ role_instructions }}"
                ),
                instance_template="{{ task }}",
                step_limit=role.step_limit,
                cost_limit=cost_limit,
                wall_time_limit_seconds=time_limit,
                output_path=output,
            )
            record = parent.run_record
            tracking = (
                record.store.track(child, run_id=run_id, parent_id=record.id, role=name) if record else nullcontext()
            )
            with tracking:
                result = child.run(arguments["task"], role_name=name, role_instructions=role.instructions)
            status = result["exit_status"]
            summary = result.get("submission", "")[:3500]
        except StorageError:
            raise
        except Exception as error:
            status = type(error).__name__
            summary = ""
        finally:
            if child is not None:
                parent.cost += child.cost
        return _observation(
            {
                "run_id": run_id,
                "role": name,
                "status": status,
                "summary": summary,
                "cost": child.cost if child is not None else 0,
                "turns": child.n_calls if child is not None else 0,
                "trajectory": str(output) if output is not None and output.is_file() else None,
            },
            status=int(status != "Submitted"),
        )

    registry.register(
        ToolSpec(
            "subagents_list",
            "Find user-configured roles for independent work. Use next_offset to list more.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
                "additionalProperties": False,
            },
        ),
        list_roles,
    )
    registry.register(
        ToolSpec(
            "subagent_run",
            "Create a fresh subagent of a configured role and wait for its result. Include all required task context.",
            {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "task": {"type": "string", "minLength": 1, "maxLength": 16_000},
                },
                "required": ["role", "task"],
                "additionalProperties": False,
            },
        ),
        run_role,
    )
