"""Cover reviewed runtime boundary regressions without external model requests."""

import json
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from vera.agents.default import DefaultAgent
from vera.agents.interactive import InteractiveAgent
from vera.desktop import streaming
from vera.desktop.worker import DesktopAgent
from vera.environments.local import LocalEnvironment
from vera.exceptions import FormatError, UserInterruption
from vera.models.litellm_model import LitellmModel
from vera.models.litellm_response_model import LitellmResponseModel
from vera.models.test_models import DeterministicModel, DeterministicToolcallModel
from vera.run import cli
from vera.runtime import open_agent_runtime
from vera.user_context import UserContext


def make_agent(agent_class=DefaultAgent, model=None, **kwargs):
    """Construct an offline agent; callers replace any action they exercise."""
    return agent_class(
        model or DeterministicModel(outputs=[], cost_per_call=0),
        LocalEnvironment(),
        system_template="Test instructions.",
        instance_template="{{task}}",
        cost_limit=0,
        **kwargs,
    )


def test_partial_usage_is_counted_on_normal_and_billed_format_error_paths(monkeypatch):
    agent = make_agent(max_consecutive_format_errors=1)
    monkeypatch.setattr(
        agent.model,
        "query",
        Mock(return_value={"role": "assistant", "extra": {"usage_reported": True, "usage": {"output": 4}}}),
    )
    agent.query()
    error = FormatError({"role": "assistant", "extra": {"cost": 0.25, "usage_reported": True, "usage": {"input": 9}}})
    monkeypatch.setattr(agent.model, "query", Mock(side_effect=error))
    assert agent.run("Stop on this format error")["exit_status"] == "RepeatedFormatError"
    assert agent.cost == 0.25
    assert agent.token_usage == {
        "input": 9,
        "output": 4,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 0,
        "reportedCalls": 2,
    }


def test_text_final_with_actions_still_confirms_and_emits_one_real_observation(monkeypatch):
    agent = make_agent(InteractiveAgent, DeterministicToolcallModel(outputs=[]), mode="confirm")
    confirmation = Mock()
    execution = Mock(return_value={"output": "approved result", "returncode": 0, "exception_info": ""})
    monkeypatch.setattr(agent, "_ask_confirmation_or_interrupt", confirmation)
    monkeypatch.setattr(agent, "_execute_action", execution)
    message = {
        "role": "assistant",
        "extra": {"text_final": True, "actions": [{"command": "unused", "tool_call_id": "call_1"}]},
    }
    agent.execute_actions(message)
    confirmation.assert_called_once_with(["unused"], tool_calls=[])
    execution.assert_called_once()
    assert len(agent.messages) == 1 and "approved result" in agent.messages[0]["content"]
    assert "not executed" not in agent.messages[0]["content"]
    confirmation.side_effect = UserInterruption({"role": "user", "content": "Denied"})
    with pytest.raises(UserInterruption):
        agent.execute_actions(message)
    assert execution.call_count == 1


def test_denied_action_after_format_recovery_does_not_emit_another_retry(monkeypatch):
    frames = []
    monkeypatch.setattr("vera.desktop.worker.send", lambda kind, **fields: frames.append({"type": kind, **fields}))
    agent = make_agent(DesktopAgent, mode="confirm", confirm_exit=False)
    outcomes = iter(
        [
            FormatError({"role": "assistant", "extra": {}}),
            {"role": "assistant", "extra": {"actions": [{"command": "unused"}]}},
            {"role": "assistant", "content": "done", "extra": {"text_final": True}},
        ]
    )

    def query(_messages):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(agent.model, "query", query)
    monkeypatch.setattr(
        agent,
        "_ask_confirmation_or_interrupt",
        Mock(side_effect=UserInterruption({"role": "user", "content": "Denied"})),
    )
    assert agent.run("Test denied action")["exit_status"] == "Submitted"
    assert [row for row in frames if row["type"] == "retry"] == [{"type": "retry", "reason": "format"}]
    assert agent.n_consecutive_format_errors == 0


def test_wsl_uses_absolute_cwd_and_forwards_only_explicit_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WSLENV", "KEEP/p")
    process = Mock(returncode=0)
    process.communicate.return_value = ("ok", None)
    popen = Mock(return_value=process)
    monkeypatch.setattr("vera.environments.local.subprocess.Popen", popen)
    shell = ["wsl.exe", "--distribution", "Fixture", "--exec", "bash"]
    environment = LocalEnvironment(cwd=".", env={"EXPLICIT": "value"}, shell_command=shell)
    assert environment.execute({"command": "printf ok"})["returncode"] == 0
    args, options = popen.call_args
    assert args[0][:3] == ["wsl.exe", "--cd", str(tmp_path.resolve())]
    assert args[0][-5:] == ["bash", "--noprofile", "--norc", "-c", "printf ok"]
    assert shell == ["wsl.exe", "--distribution", "Fixture", "--exec", "bash"]
    shared = options["env"]["WSLENV"].split(":")
    assert "KEEP/p" in shared and "EXPLICIT" in shared and "PATH" not in shared
    if os.name == "nt":
        assert {"PYTHONIOENCODING", "PYTHONUTF8"} <= set(shared)


@pytest.mark.parametrize("identity", [{"provider": "custom"}, {"modelId": "custom"}, {}])
def test_partial_usage_identity_falls_back_to_selected_model(monkeypatch, identity):
    frames = []
    monkeypatch.setattr(streaming, "send", lambda kind, **fields: frames.append((kind, fields)))
    model = streaming.StreamingChatModel(model_name="openai/fixture", cost_tracking="tokens", usage_identity=identity)
    model._desktop_request_id = "request"
    result = model._calculate_cost({"usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    assert result["usage"]["totalTokens"] == 15
    message = frames[0][1]["message"]
    assert message["provider"] == identity.get("provider", "openai")
    assert message["model"] == identity.get("modelId", "fixture")


@pytest.mark.parametrize(
    ("adapter", "base"),
    [(streaming.StreamingChatModel, LitellmModel), (streaming.StreamingResponsesModel, LitellmResponseModel)],
)
@pytest.mark.parametrize("failure", ["request", "iteration", "local", "empty"])
def test_stream_failure_observation_stays_at_provider_boundary(monkeypatch, adapter, base, failure):
    frames = []
    monkeypatch.setattr(streaming, "send", lambda kind, **fields: frames.append((kind, fields)))
    closed = []

    def chunks():
        try:
            if failure == "iteration":
                raise RuntimeError("provider iteration")
            if failure == "local":
                # These malformed objects trigger local attribute/key validation.
                yield (
                    SimpleNamespace()
                    if base is LitellmModel
                    else {"type": "response.output_item.added", "item": {"type": "function_call"}}
                )
        finally:
            closed.append(True)

    if failure == "request":
        query = Mock(side_effect=RuntimeError("provider request"))
    else:
        query = Mock(side_effect=lambda *_args, **_kwargs: chunks())
    monkeypatch.setattr(base, "_query", query)
    model = adapter(model_name="openai/fixture", cost_tracking="tokens")
    with pytest.raises((RuntimeError, AttributeError, KeyError, ValueError)):
        model._query([])
    failures = [frame for frame in frames if frame[0] == "model_failure"]
    assert len(failures) == int(failure != "local")
    assert bool(closed) == (failure != "request")


def test_failure_reporting_preserves_original_error_when_output_closes(monkeypatch):
    model = streaming.StreamingChatModel(model_name="openai/fixture", cost_tracking="tokens")
    monkeypatch.setattr(streaming, "send", Mock(side_effect=BrokenPipeError("worker closed")))
    original = RuntimeError("provider failed")
    with pytest.raises(RuntimeError) as caught:
        model._provider_call(Mock(side_effect=original), [])
    assert caught.value is original


@pytest.mark.parametrize(("cost_limit", "wall_time"), [(0, 0), (2, 12)])
def test_cli_goal_zero_budgets_preserve_per_turn_limits(monkeypatch, tmp_path, cost_limit, wall_time):
    config = {
        "model": {"model_class": "deterministic", "model_name": "fixture", "outputs": []},
        "agent": {"mode": "yolo", "cost_limit": cost_limit, "wall_time_limit_seconds": wall_time},
        "environment": {"cwd": str(tmp_path)},
        "plugins": {"enabled": False},
        "goal": {"directory": str(tmp_path / "goals"), "max_turns": 0, "cost_limit": 0, "timeout": 0},
    }
    monkeypatch.setattr(cli, "configure_if_first_time", lambda: None)
    monkeypatch.setattr(cli, "get_config_from_spec", lambda _spec: deepcopy(config))
    captured = []

    def run_task(selected, *_args):
        captured.append(selected["agent"])
        return SimpleNamespace(
            messages=[{"role": "exit", "extra": {"exit_status": "Submitted"}}],
            model=DeterministicModel(outputs=[]),
            cost=0.2,
        )

    verdicts = iter(["continue", "done"])
    monkeypatch.setattr(cli, "_run_task", run_task)
    monkeypatch.setattr(
        "vera.modes.goals.judge_goal", lambda *_args: {"verdict": next(verdicts), "reason": "fixture", "cost": 0}
    )
    result = CliRunner().invoke(cli.app, ["-c", "fixture", "-t", "/goal Complete fixture", "--exit-immediately"])
    assert result.exit_code == 0, result.output + repr(result.exception)
    assert len(captured) == 2
    assert all(row["cost_limit"] == cost_limit and row["wall_time_limit_seconds"] == wall_time for row in captured)


@pytest.mark.parametrize("context_config", [None, {}, {"directory": None}, {"directory": ""}])
def test_empty_context_configuration_uses_default_profile(monkeypatch, tmp_path, context_config):
    monkeypatch.setattr("vera.runtime.USER_CONTEXT_DIRECTORY", tmp_path / "context")
    UserContext(tmp_path / "context").save({"kind": "rule", "title": "Rule", "content": "USE_DEFAULT_CONTEXT"})
    config = {
        "model": {"model_class": "deterministic", "model_name": "fixture", "outputs": []},
        "agent": {"system_template": "Instructions", "instance_template": "{{task}}"},
        "environment": {"cwd": str(tmp_path)},
        "user_context": context_config,
        "plugins": {"enabled": False},
    }
    with open_agent_runtime(config, default_type="default") as runtime:
        assert "USE_DEFAULT_CONTEXT" in runtime.agent._render_template(runtime.agent.config.system_template)


@pytest.mark.parametrize("entry", ["invalid", [], None, {"id": ""}, {"id": 0}, {"id": False}])
def test_context_rejects_invalid_entries_without_creating_profile(tmp_path, entry):
    context = UserContext(tmp_path / "context")
    if isinstance(entry, dict):
        entry = {"kind": "rule", "title": "Rule", "content": "Keep me"} | entry
    with pytest.raises(ValueError):
        context.save(entry)
    assert not context.path.exists()


@pytest.mark.parametrize(
    "persisted",
    [
        "",
        "[]",
        '{"entries": null}',
        '{"entries": [null]}',
        '{"entries": [{}]}',
        json.dumps({"entries": [{"id": "valid", "kind": "rule", "title": "Rule", "content": "Content"}]}),
    ],
)
def test_context_corrupt_state_has_clear_error_and_is_never_overwritten(tmp_path, persisted):
    context = UserContext(tmp_path)
    context.path.write_text(persisted, encoding="utf-8")
    for operation in (
        context.entries,
        context.render,
        lambda: context.save({"kind": "rule", "title": "New", "content": "Rule"}),
    ):
        with pytest.raises(ValueError, match="entries.json"):
            operation()
        assert context.path.read_text(encoding="utf-8") == persisted


@pytest.mark.parametrize("adapter", ["openrouter", "portkey", "portkey_response", "litellm"])
@pytest.mark.parametrize("has_usage", [True, False])
def test_token_mode_retains_usage_without_looking_up_prices(monkeypatch, adapter, has_usage):
    from vera.models import get_model_class

    adapter_class = get_model_class("fixture", adapter)
    config_class = {
        "openrouter": "vera.models.openrouter_model.OpenRouterModelConfig",
        "portkey": "vera.models.portkey_model.PortkeyModelConfig",
        "portkey_response": "vera.models.portkey_response_model.PortkeyResponseAPIModelConfig",
        "litellm": "vera.models.litellm_model.LitellmModelConfig",
    }[adapter]
    from importlib import import_module

    module_name, _, name = config_class.rpartition(".")
    configuration = getattr(import_module(module_name), name)(model_name="fixture", cost_tracking="tokens")
    configuration = type(configuration).model_validate(configuration.model_dump())
    model = object.__new__(adapter_class)
    model.config = configuration
    price_lookup = Mock(side_effect=AssertionError("Token-only mode must not look up prices"))
    monkeypatch.setattr("litellm.cost_calculator.completion_cost", price_lookup)
    raw = {"prompt_tokens": 10, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 3}}
    if not has_usage:
        raw = None
    response = {"usage": raw} if adapter in {"openrouter", "litellm"} else SimpleNamespace(usage=raw)
    result = model._calculate_cost(response)
    assert result["cost"] == 0 and result["cost_known"] is False and result["usage_reported"] is has_usage
    assert result["usage"]["totalTokens"] == (15 if has_usage else 0)
    assert result["usage"]["cacheRead"] == (3 if has_usage else 0)
    price_lookup.assert_not_called()


@pytest.mark.parametrize("bounded_parent", [False, True])
def test_subagent_zero_defaults_preserve_parent_budget_inheritance(monkeypatch, bounded_parent):
    from vera.agents import subagents
    from vera.tools import ToolRegistry

    parent = make_agent(model=DeterministicToolcallModel(outputs=[]))
    parent._start_time = 98
    if bounded_parent:
        parent.config.cost_limit = 2
        parent.cost = 0.5
        parent.config.wall_time_limit_seconds = 10
    monkeypatch.setattr(subagents.time, "time", lambda: 100)
    model = DeterministicToolcallModel(
        outputs=[
            {"role": "assistant", "extra": {"actions": [{"tool": "subagent_finish", "arguments": {"summary": "done"}}]}}
        ]
    )
    model.bind_tool_registry = lambda _registry: None
    monkeypatch.setattr(subagents, "get_model", lambda **_kwargs: model)
    captured = []
    original_init = subagents._DelegatedAgent.__init__

    def initialize(child, *args, **kwargs):
        captured.append(kwargs)
        original_init(child, *args, **kwargs)

    monkeypatch.setattr(subagents._DelegatedAgent, "__init__", initialize)
    registry = ToolRegistry()
    roles = subagents.SubagentConfig(roles={"reviewer": {"description": "Review", "instructions": "Return facts"}})
    subagents.register_subagent_tools(registry, parent, roles, {}, {})
    result = registry.execute({"tool": "subagent_run", "arguments": {"role": "reviewer", "task": "Check facts"}})
    assert json.loads(result["output"])["status"] == "Submitted"
    assert captured[0]["step_limit"] == 0
    assert captured[0]["cost_limit"] == (1.5 if bounded_parent else 0)
    assert captured[0]["wall_time_limit_seconds"] == (8 if bounded_parent else 0)
