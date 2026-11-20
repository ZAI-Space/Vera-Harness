"""Read-only snapshots and observation events for existing agent implementations."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from enum import Enum


class AgentStatus(str, Enum):
    """Observed execution phase; these values never control the agent loop."""

    IDLE = "idle"
    RUNNING = "running"
    QUERYING = "querying"
    EXECUTING = "executing"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentState:
    """Detached snapshot: changing nested message dictionaries cannot affect execution.

    Messages and counters are projected from the original agent. Pending tool ids
    describe the whole action batch, including actions waiting for confirmation.
    No streaming response, durable checkpoint or pause/resume support is implied.
    """

    status: AgentStatus = AgentStatus.IDLE
    is_running: bool = False
    turn_count: int = 0
    messages: tuple[dict, ...] = ()
    cost: float = 0.0
    n_calls: int = 0
    n_consecutive_format_errors: int = 0
    pending_tool_calls: tuple[str, ...] = ()
    exit_status: str = ""
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Return a JSON-compatible snapshot using the existing message dictionary format."""
        snapshot = asdict(self)
        snapshot["status"] = self.status.value
        snapshot["messages"] = list(snapshot["messages"])
        snapshot["pending_tool_calls"] = list(snapshot["pending_tool_calls"])
        return snapshot


@dataclass(frozen=True)
class AgentEvent:
    """Lifecycle observation with a detached state snapshot and event-specific details."""

    type: str
    sequence: int
    state: AgentState
    details: dict

    def to_dict(self) -> dict:
        """Return an independent JSON-compatible event for optional external logging."""
        return {
            "type": self.type,
            "sequence": self.sequence,
            "state": self.state.to_dict(),
            "details": deepcopy(self.details),
        }
