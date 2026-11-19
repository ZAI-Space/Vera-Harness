"""State observation contracts tested with deterministic models and real Bash execution."""

import json

import pytest
from jinja2 import UndefinedError

from vera.agents import get_agent
from vera.agents.default import DefaultAgent
from vera.agents.interactive import InteractiveAgent
from vera.agents.state import AgentStatus
from vera.agents.stateful import StatefulAgent
from vera.environments.local import LocalEnvironment
from vera.exceptions import FormatError
from vera.models.test_models import DeterministicModel, make_output

CONFIG = {"system_template": "Use Bash.", "instance_template": "{{task}}", "cost_limit": 0}
FINISH = {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo done"}


def make_agent(outputs=None, **config):
    return StatefulAgent(
        DeterministicModel(outputs=outputs or [make_output("Finish", [FINISH])]),
        LocalEnvironment(),
        **(CONFIG | config),
    )


@pytest.mark.parametrize(
    ("agent_type", "original_class", "options"),
    [
        ("stateful", DefaultAgent, {}),
        ("stateful_interactive", InteractiveAgent, {"mode": "yolo", "confirm_exit": False}),
    ],
)
def test_observation_preserves_execution_and_tracks_action_batches(agent_type, original_class, options):
    outputs = [
        make_output(
            "Two actions",
            [
                {"command": "echo first", "tool_call_id": "tool_1"},
                {"command": "echo second", "tool_call_id": "tool_2"},
            ],
        ),
        make_output("Finish", [FINISH]),
    ]
    original = original_class(DeterministicModel(outputs=outputs), LocalEnvironment(), **CONFIG, **options)
    agent = get_agent(
        DeterministicModel(outputs=outputs), LocalEnvironment(), CONFIG | options | {"agent_class": agent_type}
    )
    events = []
    agent.subscribe(events.append)
    assert agent.state.status == AgentStatus.IDLE

    assert agent.run("Compare adapters") == original.run("Compare adapters")
    assert [(msg.get("role"), msg.get("content")) for msg in agent.messages] == [
        (msg.get("role"), msg.get("content")) for msg in original.messages
    ]
    assert (agent.cost, agent.n_calls) == (original.cost, original.n_calls)
    assert agent.state.status == AgentStatus.COMPLETED
    assert agent.state.exit_status == "Submitted"
    assert agent.state.turn_count == 2
    assert not agent.state.is_running
    assert not agent.state.pending_tool_calls
    assert events[0].type == "agent_start"
    assert events[-1].type == "agent_end"
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert all(event.state.status == AgentStatus.QUERYING for event in events if event.type == "query_start")
    batches = [event.state for event in events if event.type == "tools_start"]
    assert batches[0].status == AgentStatus.EXECUTING
    assert batches[0].pending_tool_calls == ("tool_1", "tool_2")
    assert all(not event.state.pending_tool_calls for event in events if event.type == "tools_end")
    assert json.loads(json.dumps(agent.state.to_dict()))["status"] == "completed"
    assert "agent_state" not in agent.serialize()["info"]


class ErrorThenFinishModel(DeterministicModel):
    """Produce a configurable number of billed format errors before a valid result."""

    def __init__(self, errors):
        super().__init__(outputs=[make_output("Finish", [FINISH])])
        self.errors_remaining = errors

    def query(self, messages, **kwargs):
        if self.errors_remaining:
            self.errors_remaining -= 1
            raise FormatError({"role": "user", "content": "Invalid format", "extra": {"cost": 0.25}})
        return super().query(messages, **kwargs)


@pytest.mark.parametrize(
    ("errors", "expected_status", "exit_status"),
    [(1, AgentStatus.COMPLETED, "Submitted"), (3, AgentStatus.FAILED, "RepeatedFormatError")],
)
def test_format_recovery_keeps_original_limits_and_charges(errors, expected_status, exit_status):
    agent = StatefulAgent(ErrorThenFinishModel(errors), LocalEnvironment(), **CONFIG, max_consecutive_format_errors=2)
    assert agent.run("Recover when permitted")["exit_status"] == exit_status
    assert agent.state.status == expected_status
    assert agent.state.n_calls == 2
    assert agent.state.cost == (1.25 if errors == 1 else 0.5)
    assert agent.state.error_message == (None if errors == 1 else "RepeatedFormatError")
    assert not agent.state.is_running


def test_budget_stop_and_reused_run_keep_existing_counter_semantics():
    limited = make_agent(outputs=[make_output("Wait", [])], step_limit=1)
    assert limited.run("Stop at the original limit")["exit_status"] == "LimitsExceeded"
    assert limited.state.status == AgentStatus.STOPPED
    assert limited.state.n_calls == 1
    assert limited.state.error_message is None

    reusable = make_agent(outputs=[make_output("First", [FINISH]), make_output("Second", [FINISH])])
    reusable.run("First")
    first = reusable.state
    reusable.run("Second")
    assert reusable.state.n_calls == 2  # Existing run() budgets accumulate; the adapter does not reset them.
    assert reusable.state.turn_count == 1
    assert first.n_calls == 1
    assert first.messages[1]["content"] == "First"
    assert reusable.state.messages[1]["content"] == "Second"


class FailingEnvironment(LocalEnvironment):
    """Raise an execution failure to exercise the original loop's exception path."""

    def execute(self, action, cwd=""):
        raise RuntimeError("environment failure")


class InterruptedModel(DeterministicModel):
    """Raise an uncaught user interrupt at the model boundary."""

    def query(self, messages, **kwargs):
        raise KeyboardInterrupt


def test_failures_and_interrupts_propagate_and_clear_pending_state():
    failed = StatefulAgent(DeterministicModel(outputs=[make_output("Run", [FINISH])]), FailingEnvironment(), **CONFIG)
    events = []
    failed.subscribe(events.append)
    with pytest.raises(RuntimeError, match="environment failure"):
        failed.run("Fail")
    assert failed.state.status == AgentStatus.FAILED
    assert failed.state.exit_status == "RuntimeError"
    assert "environment failure" in failed.state.error_message
    assert not failed.state.pending_tool_calls
    assert events[-1].type == "agent_end"
    assert not events[-1].state.is_running

    interrupted = StatefulAgent(InterruptedModel(outputs=[]), LocalEnvironment(), **CONFIG)
    with pytest.raises(KeyboardInterrupt):
        interrupted.run("Interrupt")
    assert interrupted.state.status == AgentStatus.CANCELLED
    assert not interrupted.state.is_running


def test_listener_and_snapshot_isolation_and_unsubscribe(caplog):
    agent = make_agent()
    events = []

    def mutate_snapshot(event):
        event.details["mutated"] = True
        if event.state.messages:
            event.state.messages[0]["content"] = "Observer mutation"

    def failing_listener(event):
        raise ValueError("observer failure")

    unsubscribe = agent.subscribe(mutate_snapshot)
    stop_failing = agent.subscribe(failing_listener)
    stop_recording = agent.subscribe(events.append)
    assert agent.run("Observe")["exit_status"] == "Submitted"
    assert "observer failure" in caplog.text
    assert all("mutated" not in event.details for event in events)
    assert agent.messages[0]["content"] == "Use Bash."
    snapshot = agent.state
    snapshot.messages[0]["content"] = "Detached change"
    assert agent.state.messages[0]["content"] == "Use Bash."
    for stop in (unsubscribe, stop_failing, stop_recording):
        stop()
        stop()
    event_count = len(events)
    agent.add_messages({"role": "user", "content": "After unsubscribe"})
    assert len(events) == event_count
    assert agent.state.messages[-1]["content"] == "After unsubscribe"


def test_initialization_and_save_errors_leave_observer_settled(tmp_path):
    invalid_template = make_agent(instance_template="{{missing_variable}}")
    with pytest.raises(UndefinedError):
        invalid_template.run("Cannot render")
    assert invalid_template.state.status == AgentStatus.FAILED
    assert invalid_template.state.n_calls == 0
    assert not invalid_template.state.is_running

    blocker = tmp_path / "file-not-directory"
    blocker.write_text("Existing file", encoding="utf-8")
    invalid_output = make_agent(output_path=blocker / "trajectory.json")
    with pytest.raises(FileExistsError):
        invalid_output.run("Cannot save")
    assert invalid_output.state.status == AgentStatus.FAILED
    assert invalid_output.state.exit_status == "FileExistsError"
    assert not invalid_output.state.is_running
    assert not invalid_output.state.pending_tool_calls
