"""Exercise project selection and terminal commands with real files and prompt input."""

import json
import subprocess
import time
from copy import deepcopy
from threading import Thread

import pytest
from prompt_toolkit import PromptSession
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from tests.conftest import create_symlink
from tests.run.test_plugins import write_market, write_plugin
from tests.run.test_skill_tools import write_skill
from vera.agents.interactive import InteractiveAgent
from vera.environments.local import LocalEnvironment
from vera.exceptions import InterruptAgentFlow
from vera.models.openrouter_model import OpenRouterModel
from vera.terminal.files import MAX_FILE_BYTES
from vera.terminal.session import TerminalSession
from vera.terminal.ui import TerminalCompleter, bind_session, completion_context, read_task
from vera.tools import ToolError


@pytest.fixture
def session(tmp_path):
    """An isolated project with project skills, a model profile and a configured role."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src/hello.py").write_text("print('文件内容 {{literal}}')", encoding="utf-8")
    (tmp_path / "space name.md").write_text("file with spaces", encoding="utf-8")
    write_skill(tmp_path / ".agents/skills", "review", "Inspect changed code.")
    return TerminalSession(
        {
            "model": {"model_class": "openrouter", "model_name": "fixture"},
            "terminal": {"models": {"fast": {"model_class": "openrouter", "model_name": "fast-model"}}},
            "plugins": {"directory": str(tmp_path / "plugins")},
            "mcp_servers": {"docs": {"command": "must-not-start"}},
            "subagents": {"roles": {"reviewer": {"description": "Review code", "instructions": "Review carefully."}}},
            "agent": {"agent_class": "stateful", "system_template": "Use tools.", "instance_template": "{{task}}"},
            "sandbox": {"mode": "local", "workspace": str(tmp_path)},
        },
        tmp_path,
    )


def test_git_file_selection_filters_ignored_credentials_and_preserves_literal_context(tmp_path, session):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    for name in ("ignored.txt", ".env", "private.key", "credentials.json"):
        (tmp_path / name).write_text("sensitive or ignored", encoding="utf-8")
    assert session.files.list("HELLO") == ["src/hello.py"]
    assert not {"ignored.txt", ".env", "private.key", "credentials.json"} & set(session.files.list())
    task = session.process('Review @src/hello.py and @"space name.md" and @src/hello.py').task
    records = json.loads(task.split("permission grants):\n")[1])
    assert records == [
        {"path": "src/hello.py", "content": "print('文件内容 {{literal}}')"},
        {"path": "space name.md", "content": "file with spaces"},
    ]
    assert session.files.attach(r"email@example.org and \@literal") == r"email@example.org and \@literal"
    assert session.files.list(limit=0) == []


@pytest.mark.parametrize(
    "name", ["../outside", "/absolute", "C:/file", "src\\hello.py", ".env", "file:stream", "missing"]
)
def test_invalid_references_reject_entire_task(session, name):
    with pytest.raises(ToolError):
        session.process(f"Read @src/hello.py @{name}")


def test_file_limits_binary_and_deleted_selections(tmp_path, session):
    for name, content in (
        ("binary.dat", b"hello\0world"),
        ("encoding.txt", b"\xff"),
        ("large.txt", b"a" * (MAX_FILE_BYTES + 1)),
    ):
        (tmp_path / name).write_bytes(content)
        with pytest.raises(ToolError):
            session.process(f"Read @{name}")
    for index in range(11):
        (tmp_path / f"file{index}.txt").write_bytes(b"a" * MAX_FILE_BYTES)
    with pytest.raises(ToolError, match="128 KiB"):
        session.files.attach("Read", [f"file{index}.txt" for index in range(5)])
    with pytest.raises(ToolError, match="at most 10"):
        session.files.attach("Read", [f"file{index}.txt" for index in range(11)])
    (tmp_path / "src/hello.py").unlink()
    with pytest.raises(ToolError, match="unavailable"):
        session.process("Read @src/hello.py")


def test_project_links_cannot_escape_workspace(tmp_path, session):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside project", encoding="utf-8")
    create_symlink(tmp_path / "linked.txt", outside)
    assert "linked.txt" not in session.files.list()
    with pytest.raises(ToolError, match="unavailable"):
        session.process("Read @linked.txt")


def test_commands_validate_atomically_and_keep_runtime_snapshots_independent(session):
    original = deepcopy(session.config)
    assert session.process("/help").kind == "message"
    assert session.process("/new").kind == "new"
    assert session.process("/stop").kind == "stop"
    assert session.process("//literal").task == "/literal"
    for command in (
        "/skill review,unknown",
        "/mcp unknown",
        "/permissions auto invalid",
        "/subagent none task",
        "/model unknown",
        "/unknown",
        "/stop extra",
        "/skill ,",
    ):
        with pytest.raises(ToolError):
            session.process(command)
    assert session.config == original and session.skills == [] and session.mcp is None
    session.process("/skill\treview")
    assert session.process("\n ").kind == "message"
    session.process("/mcp none")
    session.process("/model fast")
    session.process("/permissions readonly local")
    config = session.runtime_config()
    assert config["permissions"] == {"mode": "read-only"}
    assert config["model"]["model_name"] == "fast-model"
    assert config["mcp_selection"] == []
    assert config["agent"]["agent_class"] == "stateful_interactive"
    assert config["agent"]["mode"] == "confirm"
    config["model"]["model_name"] = "outside mutation"
    assert session.config["model"]["model_name"] == "fast-model"
    task = session.process('/subagent reviewer Review @"space name.md"').task
    assert "file with spaces" in task and "Inspect changed code." in task and '"reviewer"' in task
    session.process("/subagent none")
    session.process("/skill none")
    assert session.process("plain task").task == "plain task"
    session.process("/permissions auto")
    assert session.runtime_config()["agent"]["mode"] == "yolo"


def test_enabled_plugin_selection_updates_skills_without_installing_or_mutating_global_state(tmp_path, session):
    from vera.plugins import PluginManager

    write_plugin(tmp_path / "market/plugins/review")
    write_market(tmp_path / "market", [{"name": "review-kit", "source": "./plugins/review"}])
    manager = PluginManager(tmp_path / "plugins")
    manager.add_marketplace(str(tmp_path / "market"))
    manager.install_from_marketplace("review-kit", "team-market")
    assert session.catalog("/plugin") == []
    manager.set_enabled("review-kit", True)
    assert session.catalog("/plugin")[0]["name"] == "review-kit"
    session.process("/plugin none")
    assert "review-kit-review" not in {item["name"] for item in session.catalog("/skill")}
    session.process("/plugin all")
    session.process("/skill review-kit-review")
    assert "Plugin workflow body." in session.process("Review package").task
    assert manager.show("review-kit")["enabled"]
    assert "Plugin workflow body." not in session.process("/model").message


def test_actual_prompt_input_completes_and_consumes_commands_before_task(session):
    completer = TerminalCompleter(session)
    assert [item.text for item in completer.get_completions(Document("/mo"), None)] == ["/model "]
    assert [item.text for item in completer.get_completions(Document("/model fa"), None)] == ["fast"]
    assert '@"space name.md"' in [item.text for item in completer.get_completions(Document('@"space'), None)]
    assert [item.text for item in completer.get_completions(Document("/subagent reviewer Read @hell"), None)] == [
        "@src/hello.py"
    ]
    messages = []
    with create_pipe_input() as pipe:
        prompt = PromptSession(input=pipe, output=DummyOutput(), completer=completer)
        pipe.send_text('/help\n/permissions readonly\nRead @"space name.md"\n')
        assert "file with spaces" in read_task(session, prompt.prompt, messages.append)
    assert session.permission == "readonly" and len(messages) == 2
    with create_pipe_input() as pipe:
        prompt = PromptSession(input=pipe, output=DummyOutput())
        pipe.send_text("/stop\n")
        assert read_task(session, prompt.prompt, messages.append) is None
    from vera.agents.utils.prompt_user import prompt_session

    original = prompt_session.completer
    with completion_context(session):
        assert isinstance(prompt_session.completer, TerminalCompleter)
    assert prompt_session.completer is original


def test_in_task_controls_do_not_reconfigure_active_agent_or_send_commands_to_model(session):
    agent = InteractiveAgent(
        OpenRouterModel(model_name="fixture"),
        LocalEnvironment(),
        system_template="Tools.",
        instance_template="{{task}}",
    )
    messages = []
    bind_session(agent, session, messages.append)
    assert agent.input_handler("/model fast") is None
    assert agent.model.config.model_name == "fixture" and session.config["model"]["model_name"] == "fast-model"
    assert "file with spaces" in agent.input_handler('Read @"space name.md"')
    assert agent.input_handler("//literal") == "/literal"
    assert agent.input_handler("/unknown") is None
    for command in ("/stop", "/new"):
        with pytest.raises(InterruptAgentFlow) as raised:
            agent.input_handler(command)
        assert raised.value.messages[0]["extra"]["exit_status"] == "Cancelled"
    assert agent.messages == []


def test_tab_inserts_quoted_file_in_actual_multiline_prompt(session):
    """Exercise key handling rather than only requesting completion candidates."""
    with create_pipe_input() as pipe:
        prompt = PromptSession(input=pipe, output=DummyOutput(), multiline=True, completer=TerminalCompleter(session))

        def enter():
            pipe.send_text("Read @space")
            time.sleep(0.15)
            pipe.send_text("\t")
            time.sleep(0.15)
            pipe.send_text("\x1b\r")
            time.sleep(1)
            pipe.close()

        writer = Thread(target=enter, daemon=True)
        writer.start()
        try:
            assert prompt.prompt() == 'Read @"space name.md"'
        finally:
            writer.join(timeout=3)


def test_existing_human_mode_is_preserved_until_permission_command(session):
    config = deepcopy(session.config)
    config["agent"]["mode"] = "human"
    human = TerminalSession(config, session.files.root)
    assert human.runtime_config()["agent"]["mode"] == "human"
    human.process("/permissions confirm")
    assert human.runtime_config()["agent"]["mode"] == "confirm"
