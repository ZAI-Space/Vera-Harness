"""Validate host-owned job definitions and compute timezone-aware schedule instants."""

import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterError, croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vera import global_config_dir
from vera.tools import ToolError

DEFAULT_DIRECTORY = global_config_dir / "scheduler"


def parse_schedule(value: str, zone: str, now: float) -> dict:
    """Parse Hermes-style delay/interval/5-field cron/ISO schedules; return serializable UTC timing.

    Naive ISO times use the job's IANA timezone. Nonexistent wall times and past
    one-shots are rejected. Cron search is bounded to prevent impossible calendars
    consuming unbounded scheduler time. No natural-language model call is made.
    """
    try:
        location = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError("Choose a valid IANA timezone, such as Asia/Shanghai or UTC.") from None
    text = value.strip()
    match = re.fullmatch(r"(every\s+)?([1-9][0-9]{0,7})([smhdw])", text, re.IGNORECASE)
    if match:
        seconds = int(match[2]) * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[match[3].lower()]
        if seconds > 315_360_000:
            raise ToolError("Schedule duration must not exceed ten years.")
        return {"kind": "interval" if match[1] else "once", "seconds": seconds, "next": now + seconds}
    if len(text.split()) == 5:
        try:
            first = croniter(text, datetime.fromtimestamp(now, location), max_years_between_matches=5).get_next(
                datetime
            )
        except (CroniterError, ValueError, OverflowError):
            raise ToolError("Invalid five-field Cron expression, or no occurrence in the next five years.") from None
        return {"kind": "cron", "expression": text, "next": first.timestamp()}
    try:
        date = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=location)
            if datetime.fromtimestamp(date.timestamp(), location).replace(tzinfo=None) != date.replace(tzinfo=None):
                raise ValueError("Nonexistent wall time")
        instant = date.timestamp()
        if instant <= now:
            raise ValueError("Past one-shot")
    except (ValueError, OverflowError):
        raise ToolError("Use 30m, every 2h, a five-field Cron expression, or a future ISO timestamp.") from None
    return {"kind": "once", "next": instant}


def next_occurrence(schedule: dict, zone: str, slot: float, now: float) -> float | None:
    """Advance past now, coalescing missed slots instead of replaying a backlog."""
    if schedule["kind"] == "once":
        return None
    if schedule["kind"] == "interval":
        seconds = schedule["seconds"]
        return slot + (max(0, int((now - slot) // seconds)) + 1) * seconds
    return (
        croniter(
            schedule["expression"], datetime.fromtimestamp(max(slot, now), ZoneInfo(zone)), max_years_between_matches=5
        )
        .get_next(datetime)
        .timestamp()
    )


class JobSpec(BaseModel):
    """A complete scheduled task; credentials should come from provider environment variables.

    Runtime configuration is snapshotted per occurrence. Unattended execution must
    explicitly select agent.mode=yolo; confirm/human cannot answer background prompts.
    Limits apply to each invocation, including its Subagents through the normal runtime.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=100_000)
    schedule: str = Field(min_length=1, max_length=200)
    timezone: str = "UTC"
    workspace: Path
    config: dict = Field(default_factory=dict)
    skills: list[str] = Field(default_factory=list, max_length=20)
    repeat: int | None = Field(default=None, ge=1, le=1_000_000)
    grace_seconds: int = Field(default=120, ge=0, le=86400)
    catch_up: bool = True
    timeout: int = Field(default=600, ge=0, le=86400)
    step_limit: int = Field(default=50, ge=0, le=1000)
    cost_limit: float = Field(default=1, ge=0, le=100)

    @field_validator("timezone")
    @classmethod
    def check_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone name.") from None
        return value

    @model_validator(mode="after")
    def check_runtime(self):
        if self.config.get("agent", {}).get("mode") != "yolo":
            raise ValueError("Scheduled jobs require explicit config.agent.mode=yolo; confirm/human require a user.")
        if self.config.get("permissions", {}).get("mode") == "confirm":
            raise ValueError("Confirmation permissions cannot be used by an unattended job.")
        self.workspace = self.workspace.expanduser().resolve()
        return self


def utc_text(instant: float) -> str:
    """Render an instant consistently for frontend/CLI consumers."""
    return datetime.fromtimestamp(instant, timezone.utc).isoformat()
