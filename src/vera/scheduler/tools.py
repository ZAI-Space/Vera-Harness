"""Optional Hermes-style action tool; the host fixes workspace and runtime capabilities."""

import json
from copy import deepcopy
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from vera.scheduler.config import DEFAULT_DIRECTORY
from vera.scheduler.engine import service_status
from vera.scheduler.store import JobStore
from vera.tools import ToolError, ToolSpec


class SchedulerSettings(BaseModel):
    """Opt in to job management for this host-owned project; no daemon is started implicitly."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    directory: Path = DEFAULT_DIRECTORY


def register_scheduler_tools(
    registry, settings: SchedulerSettings, config: dict, workspace: Path, skills: set[str]
) -> None:
    """Register create/list/update/pause/resume/run/remove on the current project's jobs.

    The model cannot select config files, another project, credentials or execution
    permissions. Background snapshots require an already-yolo host configuration.
    Scheduled workers disable this tool so recurring work cannot create more schedules.
    """
    store = JobStore(settings.directory)
    project = workspace.expanduser().resolve()

    def manage(arguments: dict) -> dict:
        action = arguments["action"]
        if action == "list":
            result = [row for row in store.list() if Path(row["workspace"]) == project]
        elif action == "create":
            if not arguments.get("prompt") or not arguments.get("schedule"):
                raise ToolError("Creating a job requires prompt and schedule.")
            selected = arguments.get("skills", [])
            if set(selected) - skills:
                raise ToolError("Choose skills available to this project.")
            snapshot = deepcopy(config)
            snapshot["scheduler"] = {"enabled": False}
            result = store.create(
                {
                    "name": arguments.get("name", "Scheduled task"),
                    "prompt": arguments["prompt"],
                    "schedule": arguments["schedule"],
                    "timezone": arguments.get("timezone", "UTC"),
                    "skills": selected,
                    "repeat": arguments.get("repeat"),
                    "workspace": project,
                    "config": snapshot,
                }
            )
        else:
            key = arguments.get("job_id")
            if not key or Path(store.get(key)["workspace"]) != project:
                raise ToolError("Choose a scheduled job from the current project.")
            if action == "update":
                value = store.definition(key).model_dump(mode="json")
                for name in ("name", "prompt", "schedule", "timezone", "skills", "repeat"):
                    if name in arguments:
                        value[name] = arguments[name]
                if set(value["skills"]) - skills:
                    raise ToolError("Choose skills available to this project.")
                result = store.update(key, value)
            else:
                result = store.control(key, action)
        return {
            "output": json.dumps({"result": result, "service": service_status(store.directory)}, ensure_ascii=False),
            "returncode": 0,
            "exception_info": "",
        }

    def validated(arguments):
        try:
            return manage(arguments)
        except ValidationError:
            raise ToolError("Invalid scheduled job; check schedule, timezone and explicit agent.mode=yolo.") from None

    registry.register(
        ToolSpec(
            "cronjob_manage",
            "Manage scheduled tasks in this project. A running scheduler service is required to execute them.",
            {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "update", "pause", "resume", "run", "remove"],
                    },
                    "job_id": {"type": "string"},
                    "name": {"type": "string"},
                    "prompt": {"type": "string"},
                    "schedule": {"type": "string"},
                    "timezone": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "repeat": {"type": ["integer", "null"], "minimum": 1},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        ),
        validated,
    )
