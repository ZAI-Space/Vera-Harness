"""Check settings against real catalogs, private persistence and SQLite readers."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from tests.run.test_plugins import write_market, write_plugin
from vera.desktop.providers import Providers
from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore
from vera.plugins import PluginManager


def test_archive_changes_notify_catalog_readers(tmp_path):
    service = DesktopService(tmp_path / "data")
    try:
        meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        for revision, method, archived in [(0, "archiveSession", True), (1, "unarchiveSession", False)]:
            cursor = service.events.sequence
            result = service.invoke(
                method,
                {"sessionId": meta["sessionId"], "sessionFile": meta["sessionFile"], "expectedRevision": revision},
            )
            assert result["archived"] is archived
            assert result["revision"] == revision + 1
            assert any(
                event["method"] == "onSessionCatalogChanged"
                for event in service.events.read(cursor, timeout=0)["events"]
            )
            assert service.invoke("querySessionCatalog", {"query": {"archived": archived}})["total"] == 1
            assert service.invoke("querySessionCatalog", {"query": {"archived": not archived}})["total"] == 0
    finally:
        service.close()


def test_channel_snapshot_has_empty_topics_and_lifecycle_fields(tmp_path):
    service = DesktopService(tmp_path / "data")
    try:
        meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        assert service.invoke("getChannelSubscriptions", {"sessionId": meta["sessionId"]}) == {
            "sessionId": meta["sessionId"],
            "topics": [],
            "generation": 0,
            "revision": 0,
            "live": False,
        }
    finally:
        service.close()


def test_model_picker_only_exposes_configured_unique_models(tmp_path):
    providers = Providers(DesktopStore(tmp_path))
    assert all(model["authed"] for model in providers.models())
    for provider in providers.list():
        identifiers = [model["id"] for model in provider["models"]]
        assert len(identifiers) == len(set(identifiers))
    providers.configure(
        {
            "id": "qa-model",
            "name": "QA model",
            "baseUrl": "http://127.0.0.1:1/v1",
            "api": "openai-completions",
            "apiKey": "local-test-credential",
            "models": [{"id": "qa-chat", "name": "QA chat"}],
        }
    )
    assert any(model["provider"] == "qa-model" for model in providers.models())
    providers.store.save("settings", "modelPrefs", {"hiddenModels": {"qa-model": ["qa-chat"]}})
    assert not any(model["provider"] == "qa-model" for model in providers.models())
    providers.store.save(
        "settings", "modelPrefs", {"hiddenProviders": ["qa-model"], "visibleModels": {"qa-model": ["qa-chat"]}}
    )
    assert any(model["provider"] == "qa-model" for model in providers.models())
    providers.save_key("qa-model", None)
    assert not any(model["provider"] == "qa-model" for model in providers.models())


def test_permission_defaults_and_explicit_session_choice_survive_restart(tmp_path):
    service = DesktopService(tmp_path / "data")
    try:
        service.invoke(
            "saveBehaviorSettings",
            {
                "settings": {
                    "defaultMode": "agent",
                    "permissionPolicy": "human",
                    "commandShell": "git-bash",
                    "defaultSandbox": None,
                }
            },
        )
        session = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        assert (
            service.invoke("getSessionSelections", {"sessionId": session["sessionId"]})["permissionPolicy"] == "human"
        )
        service.invoke("setSessionSelections", {"sessionId": session["sessionId"], "permissionPolicy": "yolo"})
    finally:
        service.close()
    restored = DesktopService(tmp_path / "data")
    try:
        assert (
            restored.invoke("getSessionSelections", {"sessionId": session["sessionId"]})["permissionPolicy"] == "yolo"
        )
    finally:
        restored.close()


def test_enabled_plugin_skills_match_settings_catalog(tmp_path):
    service = DesktopService(tmp_path / "data")
    try:
        source = write_plugin(tmp_path / "source")
        service.invoke("pluginAction", {"action": "install", "name": "review-kit", "source": str(source)})
        assert service.invoke("getLoadedResources", {})["skills"] == []
        service.invoke("pluginAction", {"action": "enable", "name": "review-kit"})
        skills = service.invoke("getLoadedResources", {})["skills"]
        assert [skill["name"] for skill in skills] == ["review-kit-review"]
        assert skills[0]["source"] == "plugin"
        assert "skill:review-kit-review" in service.invoke("getPlugins", {})[0]["capabilities"]
        service.invoke("pluginAction", {"action": "disable", "name": "review-kit"})
        assert service.invoke("getLoadedResources", {})["skills"] == []
    finally:
        service.close()


def test_marketplace_file_fetch_does_not_hold_registry_write_lock(tmp_path):
    """Observe real file export, without replacing either Git or manager methods."""
    package = write_plugin(tmp_path / "source/plugins/review")
    source = write_market(
        package.parent.parent,
        [
            {"name": "review-kit", "source": {"source": "local", "path": "plugins/review"}},
        ],
    )
    manager = PluginManager(tmp_path / "store")
    with manager._state(write=True):
        pass
    script = r"""
import sqlite3, sys
from pathlib import Path
from vera.plugins import PluginManager
manager = PluginManager(Path(sys.argv[2]))
observed = []
def audit(event, arguments):
    if event == "shutil.copytree" and Path(arguments[0]).name == "plugins":
        with sqlite3.connect(manager.database, timeout=0) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                observed.append(str(error))
            else:
                observed.append("unlocked")
                connection.rollback()
sys.addaudithook(audit)
manager.add_marketplace(sys.argv[1])
assert observed and set(observed) == {"unlocked"}, observed
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(tmp_path / "store")],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(manager.database) as connection:
        state = json.loads(connection.execute("SELECT value FROM registry WHERE id=1").fetchone()[0])
    assert "team-market" in state["marketplaces"]


def test_mcp_connection_test_discovers_real_tools_without_enabling_or_executing(tmp_path):
    service = DesktopService(tmp_path)
    try:
        service.invoke(
            "mcpConfigUpsert",
            {"name": "qa", "command": sys.executable, "args": [str(Path(__file__).with_name("mcp_fixture.py"))]},
        )
        result = service.invoke("probeMcpServer", {"name": "qa"})
        assert result["ok"] and len(result["tools"]) == 2
        saved = service.invoke("mcpConfigList", {})["global"][0]
        assert not saved["enabled"] and saved["verification"]["ok"]
        service.invoke("mcpConfigUpsert", {"name": "qa", "command": "vera-no-such-mcp-command"})
        assert service.invoke("mcpConfigList", {})["global"][0].get("verification") is None
        assert not service.invoke("probeMcpServer", {"name": "qa"})["ok"]
    finally:
        service.close()
