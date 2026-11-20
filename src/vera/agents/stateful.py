"""Observe existing agents through inheritance without changing their execution loop.

The adapters delegate each operation exactly once and propagate its return value
and exceptions. Subscribers are synchronous observers, not execution hooks: their
ordinary exceptions are logged, and they must not advance or mutate the agent.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace

from vera.agents.default import DefaultAgent
from vera.agents.interactive import InteractiveAgent
from vera.agents.state import AgentEvent, AgentState, AgentStatus


class _StateTrackingMixin:
    """Observation adapters shared by the default and interactive agent variants."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._observed_state = AgentState()
        self._listeners: dict[object, Callable[[AgentEvent], None]] = {}
        self._event_sequence = 0

    @property
    def state(self) -> AgentState:
        """Read current state without exposing the agent's live messages or counters."""
        return replace(
            self._observed_state,
            messages=tuple(deepcopy(self.messages)),
            cost=self.cost,
            n_calls=self.n_calls,
            n_consecutive_format_errors=self.n_consecutive_format_errors,
        )

    def subscribe(self, listener: Callable[[AgentEvent], None]) -> Callable[[], None]:
        """Subscribe in registration order; return an idempotent unsubscribe function.

        Each listener receives its own snapshot after the phase update. Listener
        exceptions are logged and do not change execution or stop other listeners.
        Subscribe/unsubscribe during notification affects subsequent events.
        """
        token = object()
        self._listeners[token] = listener

        def unsubscribe() -> None:
            self._listeners.pop(token, None)

        return unsubscribe

    def _emit(self, event_type: str, **details) -> None:
        self._event_sequence += 1
        if not self._listeners:
            return
        try:
            event = AgentEvent(event_type, self._event_sequence, self.state, details)
        except Exception:
            self.logger.exception("Unable to snapshot agent state for %s", event_type)
            return
        for listener in list(self._listeners.values()):
            try:
                listener(deepcopy(event))
            except Exception:
                self.logger.exception("Agent state listener failed for %s", event_type)

    def run(self, *args, **kwargs) -> dict:
        """Observe one existing run; retain the underlying transcript and budget semantics."""
        self._observed_state = AgentState(status=AgentStatus.RUNNING, is_running=True)
        try:
            self._emit("agent_start")
            result = super().run(*args, **kwargs)
        except BaseException as error:
            self._observed_state = replace(
                self._observed_state,
                status=AgentStatus.CANCELLED if isinstance(error, KeyboardInterrupt) else AgentStatus.FAILED,
                exit_status=type(error).__name__,
                error_message=f"{type(error).__name__}: {error}",
            )
            raise
        else:
            exit_status = result.get("exit_status", "")
            status = AgentStatus.STOPPED
            if exit_status == "Submitted":
                status = AgentStatus.COMPLETED
            elif exit_status == "Cancelled":
                status = AgentStatus.CANCELLED
            elif exit_status == "RepeatedFormatError":
                status = AgentStatus.FAILED
            self._observed_state = replace(
                self._observed_state,
                status=status,
                exit_status=exit_status,
                error_message=exit_status if status == AgentStatus.FAILED else None,
            )
            return result
        finally:
            self._observed_state = replace(self._observed_state, is_running=False, pending_tool_calls=())
            self._emit("agent_end")

    def step(self) -> list[dict]:
        """Count and observe turns while retaining the existing step implementation."""
        previous_status = self._observed_state.status
        self._observed_state = replace(
            self._observed_state, status=AgentStatus.RUNNING, turn_count=self._observed_state.turn_count + 1
        )
        self._emit("turn_start")
        try:
            return super().step()
        finally:
            self._observed_state = replace(self._observed_state, status=previous_status)
            self._emit("turn_end")

    def query(self) -> dict:
        """Observe agent.query(), including human-mode queries in the interactive variant."""
        previous_status = self._observed_state.status
        self._observed_state = replace(self._observed_state, status=AgentStatus.QUERYING)
        self._emit("query_start")
        try:
            return super().query()
        finally:
            self._observed_state = replace(self._observed_state, status=previous_status)
            self._emit("query_end")

    def execute_actions(self, message: dict) -> list[dict]:
        """Observe an action batch without wrapping the environment or rescheduling tools."""
        previous_status = self._observed_state.status
        actions = message.get("extra", {}).get("actions", [])
        self._observed_state = replace(
            self._observed_state,
            status=AgentStatus.EXECUTING,
            pending_tool_calls=tuple(
                action.get("tool_call_id") or f"turn_{self._observed_state.turn_count}_action_{index}"
                for index, action in enumerate(actions)
            ),
        )
        self._emit("tools_start")
        try:
            return super().execute_actions(message)
        finally:
            self._observed_state = replace(self._observed_state, status=previous_status, pending_tool_calls=())
            self._emit("tools_end")

    def add_messages(self, *messages: dict) -> list[dict]:
        """Observe appended messages after the original implementation finishes."""
        result = super().add_messages(*messages)
        self._emit("messages_added", count=len(messages))
        return result

    def _prompt_and_handle_slash_commands(self, *args, **kwargs) -> str:
        previous_status = self._observed_state.status
        self._observed_state = replace(self._observed_state, status=AgentStatus.WAITING_FOR_INPUT)
        self._emit("input_requested")
        try:
            return super()._prompt_and_handle_slash_commands(*args, **kwargs)
        finally:
            self._observed_state = replace(self._observed_state, status=previous_status)
            self._emit("input_received")


class StatefulAgent(_StateTrackingMixin, DefaultAgent):
    """DefaultAgent with observational state and lifecycle subscriptions."""


class StatefulInteractiveAgent(_StateTrackingMixin, InteractiveAgent):
    """InteractiveAgent with the same state API, including existing input prompts."""
