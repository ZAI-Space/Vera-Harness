"""Run explicit plan/goal commands through real HTTP models, files, SQLite and CLI processes."""

import json
import subprocess
import sys
from copy import deepcopy

import pytest
import yaml

from tests.run.test_skill_tools import run_cli
from tests.run.test_terminal_runtime import runtime_profile, terminal_model  # noqa: F401
from vera.exceptions import InterruptAgentFlow
from vera.modes.goals import GoalConfig, GoalStore, conversation_messages
from vera.runtime import open_agent_runtime
from vera.terminal.session import TerminalSession
from vera.terminal.ui import bind_session
from vera.tools import ToolError


def mode_config(tmp_path, terminal_model):
    """Configure production model requests against the explicit local protocol peer."""
    config = runtime_profile(tmp_path)
    config["model"].update(
        model_class="tests.run.test_terminal_runtime.TerminalFixtureModel", api_url=terminal_model["url"]
    )
    config["goal"] = {
        "directory": str(tmp_path / "goals"),
        "max_turns": 3,
        "judge_model": config["model"] | {"model_name": "judge"},
    }
    config["storage"] = {"path": str(tmp_path / "runs.sqlite3")}
    return config


def cli_mode(tmp_path, config, task):
    path = tmp_path / "modes.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    try:
        return run_cli(tmp_path, "vera", "-c", str(path), "-t", task, "--exit-immediately")
    except subprocess.CalledProcessError as error:
        raise AssertionError(error.stdout + "\n" + error.stderr) from error


def test_plan_cli_inspects_files_saves_one_plan_and_never_starts_external_services(tmp_path, terminal_model):
    config = mode_config(tmp_path, terminal_model)
    (tmp_path / "app.py").write_text("print('source unchanged')", encoding="utf-8")
    marker = tmp_path / "mcp-started.txt"
    config["mcp_servers"] = {
        "forbidden": {"command": sys.executable, "args": ["-c", f"open({str(marker)!r},'w').close()"]}
    }
    config["subagents"] = {
        "roles": {"writer": {"description": "Should not run", "instructions": "Write code", "tools": ["bash"]}}
    }
    terminal_model["actions"]["parent"] = [
        ("project_files", {"query": "app"}),
        ("project_read", {"path": "app.py"}),
        ("plan_finish", {"markdown": "# Plan\nInspect app.py.\nRun pytest after implementation.\n"}),
    ]
    result = cli_mode(tmp_path, config, "/plan Improve the app")
    assert "Plan saved:" in result.stdout
    plans = list((tmp_path / ".vera" / "plans").glob("*.md"))
    assert len(plans) == 1 and plans[0].read_text().startswith("# Plan")
    assert (tmp_path / "app.py").read_text() == "print('source unchanged')" and not marker.exists()
    for request in terminal_model["requests"]:
        assert {row["function"]["name"] for row in request["tools"]} == {"project_files", "project_read", "plan_finish"}
    assert "source unchanged" in json.dumps(terminal_model["requests"][-1])


def test_plan_capability_boundary_rejects_legacy_bash_and_secret_file_access(tmp_path, terminal_model):
    config = mode_config(tmp_path, terminal_model) | {"run_mode": "plan"}
    (tmp_path / ".env").write_text("PRIVATE=secret", encoding="utf-8")
    with open_agent_runtime(config) as runtime:
        registry = runtime.agent.tool_registry
        assert registry.execute({"command": "touch forbidden.txt"})["returncode"] == 1
        assert registry.execute({"tool": "project_read", "arguments": {"path": ".env"}})["returncode"] == 1
        assert registry.execute({"tool": "project_read", "arguments": {"path": "../outside"}})["returncode"] == 1
    assert not (tmp_path / "forbidden.txt").exists()


def test_goal_cli_continues_same_context_until_evidence_based_judge_completes(tmp_path, terminal_model):
    config = mode_config(tmp_path, terminal_model)
    terminal_model["actions"]["parent"] = [
        ("goal_turn_finish", {"summary": "Inspected project; implementation remains"}),
        ("bash", {"command": "printf verified-goal > goal-artifact.txt"}),
        ("goal_turn_finish", {"summary": "goal-artifact.txt exists with verified-goal"}),
    ]
    terminal_model["actions"]["judge"] = [
        ("goal_verdict", {"verdict": "continue", "reason": "The artifact has not been produced"}),
        ("goal_verdict", {"verdict": "done", "reason": "Actual Bash receipt proves the artifact was written"}),
    ]
    result = cli_mode(tmp_path, config, "/goal Create and verify goal-artifact.txt")
    assert "Goal completed:" in result.stdout
    assert (tmp_path / "goal-artifact.txt").read_text() == "verified-goal"
    store = GoalStore(tmp_path, settings=GoalConfig.model_validate(config["goal"]))
    state = store.read()
    assert state["status"] == "completed" and state["turns"] == 2 and not state["in_flight"]
    requests = [item for item in terminal_model["requests"] if item["model"] == "parent"]
    assert "implementation remains" in json.dumps(requests[1]["messages"])
    assert sum(row["role"] == "system" for row in requests[1]["messages"]) == 1
    assert requests[1]["messages"][-2]["role"] == "tool"
    assert all(
        {row["function"]["name"] for row in request["tools"]} == {"goal_verdict"}
        for request in terminal_model["requests"]
        if request["model"] == "judge"
    )
    from vera.storage import RunStore

    assert len(RunStore(tmp_path / "runs.sqlite3").list_runs()) == 2


def test_goal_budget_pause_resume_blocked_and_invalid_judge_never_mark_done(tmp_path, terminal_model):
    config = mode_config(tmp_path, terminal_model)
    config["goal"]["max_turns"] = 1
    terminal_model["actions"]["parent"] = [("goal_turn_finish", {"summary": "Partial work"})]
    terminal_model["actions"]["judge"] = [("goal_verdict", {"verdict": "continue", "reason": "More work remains"})]
    cli_mode(tmp_path, config, "/goal Finish all checks")
    store = GoalStore(tmp_path, settings=GoalConfig.model_validate(config["goal"]))
    assert store.status()["status"] == "paused" and store.status()["reason"] == "Goal budget exhausted"
    terminal_model["actions"]["parent"] = [("goal_turn_finish", {"summary": "Requires user input"})]
    terminal_model["actions"]["judge"] = [
        ("goal_verdict", {"verdict": "blocked", "reason": "A user decision is required"})
    ]
    cli_mode(tmp_path, config, "/goal resume")
    assert store.status()["status"] == "blocked" and store.status()["turns"] == 1
    terminal_model["actions"]["parent"] = [("goal_turn_finish", {"summary": "Still working"})]
    terminal_model["actions"]["judge"] = [("bash", {"command": "touch judge-must-not-run.txt"})]
    cli_mode(tmp_path, config, "/goal resume")
    assert store.status()["status"] == "paused" and "invalid output" in store.status()["reason"]
    assert not (tmp_path / "judge-must-not-run.txt").exists()


def test_goal_session_controls_permission_separation_and_interrupted_turn_fence(tmp_path):
    config = runtime_profile(tmp_path) | {"goal": {"directory": str(tmp_path / "goals")}}
    session = TerminalSession(config, tmp_path)
    assert session.process("/goal").kind == "message" and not (tmp_path / "goals").exists()
    assert session.process("/goal -- pause the nightly task").kind == "task"
    assert session.run_mode == "goal" and session.permission == "auto"
    assert "messages" not in session.goals.status()
    session.process("/goal pause")
    assert session.goals.status()["status"] == "paused"
    session.process("/goal resume")
    session.process("/plan Review the implementation")
    assert session.run_mode == "plan" and session.goals.status()["status"] == "paused"
    session.process("An ordinary task")
    assert session.run_mode == "normal"
    session.process("/permissions confirm")
    session.process("/goal A new goal")
    assert session.runtime_config()["agent"]["mode"] == "confirm"
    state = session.goals.read()
    session.goals.patch(state["id"], in_flight=True)
    session.goals.control("pause")
    with pytest.raises(ToolError, match="interrupted"):
        session.goals.control("resume")
    assert session.goals.status()["status"] == "interrupted"
    with pytest.raises(ToolError, match="Inspect interrupted"):
        session.goals.control("resume")
    session.goals.set("Inspected effects; proceed with a new objective")
    session.process("/goal clear")
    assert session.goals.status()["status"] == "none"
    session.process("/permissions human")
    with pytest.raises(ToolError, match="requires a model"):
        session.process("/goal Requires reasoning")


def test_in_task_plan_switch_exits_before_reassembling_capabilities(tmp_path, terminal_model):
    config = mode_config(tmp_path, terminal_model)
    session = TerminalSession(config, tmp_path)
    with open_agent_runtime(config) as runtime:
        bind_session(runtime.agent, session, lambda _: None)
        with pytest.raises(InterruptAgentFlow) as raised:
            runtime.agent.input_handler("/plan Inspect first")
        assert raised.value.messages[0]["extra"]["pending_task"].startswith("[/plan:")
        assert runtime.agent.tool_registry is None
    assert session.run_mode == "plan"


def test_goal_transcript_completes_final_tool_batch_without_mutating_original():
    from vera.models.openrouter_model import OpenRouterModel

    model = OpenRouterModel(model_name="fixture")
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "goal_turn_finish", "arguments": "{}"}}
            ],
            "extra": {"actions": [{"tool": "goal_turn_finish", "arguments": {}, "tool_call_id": "call_1"}]},
        },
        {"role": "exit", "content": "finished"},
    ]
    original = deepcopy(messages)
    joined = conversation_messages([], messages, model)
    assert joined[-1]["role"] == "tool" and joined[-1]["tool_call_id"] == "call_1"
    assert messages == original and all(row["role"] != "exit" for row in joined)


def test_goal_runtime_changes_stop_at_boundary_before_another_model_call(tmp_path, terminal_model):
    from vera.modes.goals import drive_goal
    from vera.run.cli import _run_task

    config = mode_config(tmp_path, terminal_model)
    session = TerminalSession(config, tmp_path)
    session.process("/goal Verify this project")
    terminal_model["actions"]["parent"] = [("goal_turn_finish", {"summary": "First turn verified"})]

    def run_turn(task, history, remaining):
        agent = _run_task(session.runtime_config(), task, None, None, None, session, history)
        session.set_mode("confirm")
        return agent

    drive_goal(session, run_turn, lambda _: None)
    assert session.goals.status()["status"] == "paused"
    assert "Runtime choices changed" in session.goals.status()["reason"]
    assert len(terminal_model["requests"]) == 1
    assert session.runtime_config()["agent"]["mode"] == "confirm"


def test_responses_goal_transcript_fills_only_missing_tool_receipts():
    from vera.models.openrouter_response_model import OpenRouterResponseModel

    model = OpenRouterResponseModel(model_name="fixture")
    first = {"type": "function_call", "call_id": "first", "name": "project_read", "arguments": "{}"}
    finish = {"type": "function_call", "call_id": "finish", "name": "goal_turn_finish", "arguments": "{}"}
    actions = [{"tool": row["name"], "arguments": {}, "tool_call_id": row["call_id"]} for row in (first, finish)]
    messages = [
        model.format_message(role="system", content="system"),
        model.format_message(role="user", content="goal"),
        {"object": "response", "output": [first, finish], "extra": {"actions": actions}},
        {"type": "function_call_output", "call_id": "first", "output": "File content"},
        {"role": "exit", "content": "Turn completed"},
    ]
    joined = conversation_messages([], messages, model)
    receipts = [row for row in joined if row.get("type") == "function_call_output"]
    assert [row["call_id"] for row in receipts] == ["first", "finish"]
    assert "Turn completed" in receipts[-1]["output"]
    assert len(model._prepare_messages_for_api(joined)) == 6


def test_goal_judge_receives_actual_responses_api_tool_evidence(tmp_path, terminal_model):
    from vera.modes.goals import judge_goal

    config = mode_config(tmp_path, terminal_model)
    terminal_model["actions"]["judge"] = [("goal_verdict", {"verdict": "done", "reason": "Verified command result"})]
    result = judge_goal(
        config,
        {"objective": "Verify the fixture receipt"},
        {"submission": "Finished"},
        [{"type": "function_call_output", "call_id": "receipt", "output": "Actual fixture command output: exit 0"}],
    )
    assert result["verdict"] == "done"
    evidence = json.loads(terminal_model["requests"][0]["messages"][-1]["content"])["evidence"]
    assert evidence == [{"role": "function_call_output", "content": "Actual fixture command output: exit 0"}]
