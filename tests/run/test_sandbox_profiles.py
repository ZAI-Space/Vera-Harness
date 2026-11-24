"""Exercise saved sandbox settings, real availability probes and shared runtime isolation."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event

import pytest
import yaml
from prompt_toolkit.document import Document
from pydantic import ValidationError

from tests.run.test_skill_tools import run_cli
from tests.run.test_terminal_runtime import runtime_profile
from tests.run.test_terminal_runtime import terminal_model as terminal_model
from vera.environments.sandbox import SandboxConfig, _bubblewrap, _docker
from vera.environments.sandbox_profiles import SandboxProfiles, resolve_sandbox_profile
from vera.runtime import open_agent_runtime
from vera.storage import RunStore
from vera.terminal.session import TerminalSession
from vera.terminal.ui import TerminalCompleter
from vera.tools import ToolError


def test_profile_lifecycle_validation_and_project_binding(tmp_path):
    store = SandboxProfiles(tmp_path / "settings/profiles.sqlite3")
    assert store.list_profiles() == {}
    assert store.status()["configured"] is False and not store.path.parent.exists()
    store.save("python-dev", {"mode": "docker", "docker_image": "python:3.12-slim"})
    assert store.select("python-dev", tmp_path).workspace == tmp_path.resolve()
    with pytest.raises(ToolError, match="already exists"):
        store.save("python-dev", {"mode": "bubblewrap"})
    with pytest.raises(ValidationError):
        store.save("python-dev", {"mode": "docker", "timeout": 0}, replace=True)
    assert store.select("python-dev").mode == "docker"
    store.save("python-dev", {"mode": "bubblewrap", "workspace_access": "read-only"}, replace=True)
    selected = store.select("python-dev", tmp_path)
    selected.timeout = 123
    assert store.select("python-dev").timeout == 30
    for name in ("../escape", "none", "local", "all", "UPPER", "space name"):
        with pytest.raises(ToolError):
            store.save(name, {"mode": "docker"})
    for backend in ("auto", "local"):
        with pytest.raises(ToolError, match="explicit"):
            store.save("invalid", {"mode": backend})
    store.remove("python-dev")
    assert store.list_profiles() == {}
    with pytest.raises(ToolError, match="Unknown"):
        store.select("python-dev")
    with pytest.raises(ToolError, match="Unknown"):
        store.remove("python-dev")


def test_store_transactions_preserve_concurrent_settings_and_report_corruption(tmp_path):
    store = SandboxProfiles(tmp_path / "profiles.sqlite3")
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda index: store.save(f"profile-{index}", {"mode": "docker"}), range(12)))
    assert len(store.list_profiles()) == 12
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE profiles SET config = 'invalid json' WHERE name = 'profile-0'")
    with pytest.raises(ToolError, match="unavailable"):
        store.list_profiles()
    assert store.path.exists()


def test_store_waits_for_another_connection_to_release_its_write_transaction(tmp_path, monkeypatch):
    """Keep SQLite's cross-connection waiting contract, independently of the instance lock."""
    store = SandboxProfiles(tmp_path / "profiles.sqlite3")
    store.save("existing", {"mode": "docker"})
    connect = sqlite3.connect
    writer_started = Event()

    def observe_writer(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(
            lambda statement: writer_started.set() if statement == "BEGIN IMMEDIATE" else None
        )
        return connection

    with closing(connect(store.path)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr(sqlite3, "connect", observe_writer)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(store.save, "waiting", {"mode": "bubblewrap"})
            try:
                assert writer_started.wait(timeout=5), "The second connection never attempted its write transaction"
            finally:
                blocker.commit()
            assert pending.result(timeout=5)["name"] == "waiting"
    assert set(store.list_profiles()) == {"existing", "waiting"}


def test_failed_replacement_rolls_back_and_reports_only_the_sqlite_error_name(tmp_path):
    """A real SQLite abort must preserve the previous profile and release its write lock."""
    store = SandboxProfiles(tmp_path / "profiles.sqlite3")
    store.save("existing", {"mode": "docker"})
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER reject_replacement AFTER INSERT ON profiles "
            "BEGIN SELECT RAISE(ABORT, 'private trigger diagnostic'); END"
        )
    with pytest.raises(ToolError) as error:
        store.save("existing", {"mode": "bubblewrap"}, replace=True)
    if sys.version_info >= (3, 11):
        assert "SQLITE_CONSTRAINT_TRIGGER" in str(error.value)
    else:
        assert "IntegrityError" in str(error.value)
    assert "private trigger diagnostic" not in str(error.value)
    assert store.select("existing").mode == "docker"
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute("DROP TRIGGER reject_replacement")
    store.save("existing", {"mode": "bubblewrap"}, replace=True)
    assert store.select("existing").mode == "bubblewrap"


def test_failed_first_save_rolls_back_schema_creation(tmp_path, monkeypatch):
    """Reject the first insert through SQLite itself; schema creation must roll back too."""
    store = SandboxProfiles(tmp_path / "profiles.sqlite3")
    connect = sqlite3.connect

    def reject_profile_insert(action, table, column, database, trigger):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and table == "profiles" else sqlite3.SQLITE_OK

    def restricted_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_authorizer(reject_profile_insert)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", restricted_connection)
        with pytest.raises(ToolError, match="Cannot save sandbox profile"):
            store.save("first", {"mode": "docker"})
    with closing(connect(store.path)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'profiles'").fetchall() == []
    store.save("first", {"mode": "docker"})
    assert set(store.list_profiles()) == {"first"}


def test_runtime_resolution_preserves_legacy_and_replaces_profile_options(tmp_path):
    store = SandboxProfiles(tmp_path / "profiles.sqlite3")
    store.save("review", {"mode": "docker", "workspace_access": "read-only"})
    config = {
        "sandbox_profiles": {"path": str(store.path)},
        "sandbox_profile": "review",
        "sandbox": {"mode": "local", "allow_web_tools": True, "host_mcp_servers": ["old"]},
    }
    resolved = resolve_sandbox_profile(config, tmp_path)
    assert resolved["sandbox"]["mode"] == "docker"
    assert resolved["sandbox"]["workspace"] == str(tmp_path.resolve())
    assert resolved["sandbox"]["host_mcp_servers"] == [] and not resolved["sandbox"]["allow_web_tools"]
    assert config["sandbox"]["mode"] == "local"
    assert resolve_sandbox_profile({"agent": {"mode": "human"}}) == {"agent": {"mode": "human"}}
    for name in ("", False, 0, []):
        with pytest.raises(ToolError, match="configured sandbox name"):
            resolve_sandbox_profile({"sandbox_profile": name})
    store.remove("review")
    with pytest.raises(ToolError, match="Unknown"):
        with open_agent_runtime(resolved):
            pytest.fail("Removed profile silently fell back to local execution")


def test_modes_are_independent_from_sandbox_and_empty_picker_is_disabled(tmp_path):
    config = runtime_profile(tmp_path)
    config["sandbox_profiles"] = {"path": str(tmp_path / "profiles.sqlite3")}
    session = TerminalSession(config, tmp_path)
    assert session.sandbox_status() == {
        "configured": False,
        "enabled": False,
        "reason": "Configure a sandbox in settings first.",
        "choices": [],
        "selected": None,
    }
    assert {row["name"] for row in session.catalog("/permissions")} == {"confirm", "yolo", "human"}
    assert list(TerminalCompleter(session).get_completions(Document("/sand"), None)) == []
    for mode in ("confirm", "yolo", "human"):
        session.process(f"/permissions {mode}")
        current = session.runtime_config()
        assert current["agent"]["mode"] == mode and current["sandbox"]["mode"] == "local"
    with pytest.raises(ToolError):
        session.set_mode("invented")
    assert session.permission == "human"
    assert "Configure a sandbox" in session.process("/sandbox").message
    store = SandboxProfiles.from_config(config)
    store.save("unavailable", {"mode": "docker", "workspace": str(tmp_path / "missing")})
    assert store.status()["choices"][0]["code"] == "workspace_unavailable"
    assert session.catalog("/sandbox")[0]["name"] == "unavailable"
    assert [row.text for row in TerminalCompleter(session).get_completions(Document("/sand"), None)] == ["/sandbox "]
    session.process("/sandbox none")
    assert session.runtime_config()["sandbox"] == {"mode": "local", "workspace": str(tmp_path.resolve())}


def test_settings_cli_and_missing_backends_disable_choices_without_installing(tmp_path):
    store = tmp_path / "user settings/profiles.sqlite3"
    missing = {
        "VERA_DOCKER_EXECUTABLE": str(tmp_path / "not-installed-docker"),
        "VERA_BUBBLEWRAP_EXECUTABLE": str(tmp_path / "not-installed-bwrap"),
    }
    arguments = ("sandboxes", "--store", str(store))
    assert json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *arguments, "list").stdout) == {}
    assert not store.exists()
    config = tmp_path / "profile.yaml"
    config.write_text(yaml.safe_dump({"mode": "docker", "workspace": str(tmp_path)}), encoding="utf-8")
    run_cli(tmp_path, "vera.run.utilities.extra", *arguments, "save", "python-dev", str(config))
    profiles = SandboxProfiles(store)
    profiles.save("linux-dev", {"mode": "bubblewrap", "workspace": str(tmp_path)})
    status = json.loads(run_cli(tmp_path, "vera.run.utilities.extra", *arguments, "check", **missing).stdout)
    assert status["configured"] and not status["enabled"]
    assert len(status["choices"]) == 2 and all(row["code"] == "backend_unavailable" for row in status["choices"])
    selection = tmp_path / "choose_profile.py"
    selection.write_text(
        "import json\nfrom pathlib import Path\n"
        "from vera.terminal.session import TerminalSession\n"
        f"session=TerminalSession({{'sandbox_profiles':{{'path':{str(store)!r}}}}},Path.cwd())\n"
        "try: session.select_sandbox('python-dev')\n"
        "except ValueError as error: print(str(error))\n"
        "else: raise RuntimeError('Unavailable profile accepted')\n"
        "assert session.sandbox_name is None\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(selection)],
        cwd=tmp_path,
        env=os.environ | missing,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    assert "unavailable" in result.stdout
    run_cli(tmp_path, "vera.run.utilities.extra", *arguments, "remove", "python-dev")
    assert set(profiles.list_profiles()) == {"linux-dev"}


@pytest.mark.parametrize("backend", ["docker", "bubblewrap"])
def test_named_profile_executes_shared_parent_child_runtime(tmp_path, terminal_model, backend):
    if backend == "docker" and _docker(SandboxConfig()) is None:
        pytest.skip("Local Linux Docker engine/image unavailable")
    if backend == "bubblewrap" and _bubblewrap() is None:
        pytest.skip("Linux Bubblewrap namespaces unavailable")
    config = runtime_profile(tmp_path)
    config["sandbox_profiles"] = {"path": str(tmp_path / "profiles.sqlite3")}
    SandboxProfiles.from_config(config).save("project-env", {"mode": backend, "workspace": str(tmp_path)})
    config["model"].update(
        model_class="tests.run.test_terminal_runtime.TerminalFixtureModel", api_url=terminal_model["url"]
    )
    config["subagents"] = {
        "roles": {
            "writer": {
                "description": "Write inside the project",
                "instructions": "Use only provided tools",
                "tools": ["bash"],
                "model": config["model"] | {"model_name": "child"},
            }
        }
    }
    session = TerminalSession(config, tmp_path)
    assert session.sandbox_status()["enabled"]
    session.select_sandbox("project-env")
    session.set_mode("yolo")
    snapshot = session.runtime_config()
    terminal_model["actions"]["parent"] = [
        ("subagent_run", {"role": "writer", "task": "Write scoped artifact"}),
        (
            "bash",
            {
                "command": 'test "$(cat scoped.txt)" = child-ok && echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo isolated-parent-ok'
            },
        ),
    ]
    terminal_model["actions"]["child"] = [
        ("bash", {"command": "printf child-ok > scoped.txt"}),
        ("subagent_finish", {"summary": "child file written"}),
    ]
    with open_agent_runtime(snapshot) as runtime:
        assert runtime.mode == backend
        with RunStore(tmp_path / "runs.sqlite3").track(
            runtime.agent, workspace=tmp_path, runtime_policy=runtime.policy
        ):
            assert runtime.agent.run("Run configured sandbox")["submission"] == "isolated-parent-ok\n"
        session.select_sandbox(None)
        assert runtime.mode == backend and session.runtime_config()["sandbox"]["mode"] == "local"
    assert (tmp_path / "scoped.txt").read_text() == "child-ok"
    assert snapshot["sandbox"]["mode"] == backend
    result = RunStore(tmp_path / "runs.sqlite3").list_runs()
    assert len(result) == 2 and all(row["status"] == "completed" for row in result)
    profile = tmp_path / "configured-runtime.yaml"
    profile.write_text(yaml.safe_dump(config), encoding="utf-8")
    completed = run_cli(
        tmp_path,
        "vera",
        "-c",
        str(profile),
        "--sandbox-profile",
        "project-env",
        "-t",
        "Use the named environment",
        "-y",
        "--exit-immediately",
        "-o",
        str(tmp_path / "cli.json"),
    )
    assert f"Execution mode: {backend}" in completed.stdout
    assert json.loads((tmp_path / "cli.json").read_text())["info"]["exit_status"] == "Submitted"


def test_cli_selects_saved_profile_and_rejects_conflicting_flags(tmp_path):
    config = runtime_profile(tmp_path)
    config["sandbox_profiles"] = {"path": str(tmp_path / "profiles.sqlite3")}
    SandboxProfiles.from_config(config).save("project-env", {"mode": "docker"})
    profile = tmp_path / "runtime.yaml"
    profile.write_text(yaml.safe_dump(config), encoding="utf-8")
    for extra, expected in (
        (["--sandbox-profile", "missing"], "Unknown sandbox profile"),
        (["--sandbox-profile", "project-env", "--sandbox", "local"], "not both"),
        (["--sandbox-profile", "project-env"], "unavailable"),
    ):
        with pytest.raises(subprocess.CalledProcessError) as error:
            run_cli(
                tmp_path,
                "vera",
                "-c",
                str(profile),
                "-t",
                "Run",
                *extra,
                VERA_DOCKER_EXECUTABLE=str(tmp_path / "missing-docker"),
            )
        assert expected in error.value.stderr
