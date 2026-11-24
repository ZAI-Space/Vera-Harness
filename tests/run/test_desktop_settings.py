"""Check settings against real catalogs, private persistence and SQLite readers."""

import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from tests.run.test_plugins import write_market, write_plugin
from vera.desktop.providers import Providers
from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore
from vera.plugins import PluginManager
from vera.scheduler.config import utc_text


def test_scheduled_run_snapshot_exposes_parseable_completion_time(tmp_path):
    """The renderer needs an ISO end time to display completed run durations."""
    from vera.desktop.scheduling import ScheduledTasks

    service = DesktopService(tmp_path / "data")
    try:
        scheduled = ScheduledTasks(service)
        key = scheduled.jobs.create(
            {
                "name": "History fixture",
                "prompt": "Never executed",
                "schedule": "1s",
                "workspace": str(tmp_path),
                "config": {"agent": {"mode": "yolo"}},
            },
            now=0,
        )["id"]
        execution = scheduled.jobs.claim_due(1, now=1)[0]
        assert scheduled.jobs.start(execution)
        assert service.invoke("getScheduledTasks")["runs"][0]["endedAt"] is None
        scheduled.jobs.finish(execution, "completed", {"summary": "Completed fixture"})
        run = service.invoke("getScheduledTasks")["runs"][0]
        assert run["taskId"] == key and run["status"] == "completed"
        assert run["endedAt"] == utc_text(scheduled.jobs.execution(execution)["finished_at"])
        assert datetime.fromisoformat(run["endedAt"]) >= datetime.fromisoformat(run["startedAt"])
    finally:
        service.close()


def test_market_reads_publisher_metadata_images_and_skips_incompatible_names(tmp_path):
    """One incompatible identity must not hide valid packages or their publisher artwork."""
    root = tmp_path / "source"
    package = write_plugin(root / "plugins/review", layout="codex")
    manifest = package / ".codex-plugin/plugin.json"
    value = json.loads(manifest.read_text())
    value["interface"] = {
        "displayName": "Review",
        "shortDescription": "Inspect changes",
        "composerIcon": "./assets/logo.svg",
    }
    manifest.write_text(json.dumps(value))
    (package / "assets").mkdir()
    (package / "assets/logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h10v10z"/></svg>')
    write_market(
        root,
        [
            {"name": "42unsupported", "source": "./plugins/review"},
            {"name": "review-kit", "source": "./plugins/review"},
        ],
    )
    service = DesktopService(tmp_path / "data")
    try:
        service.capabilities.plugins.add_marketplace(str(root))
        market = service.invoke("pluginMarket", {"source": "team-market"})
        assert len(market) == 1
        assert market[0]["description"] == "Review changes."
        assert market[0]["name"] == "Review"
        assert market[0]["icon"].startswith("data:image/svg+xml;base64,")
        assert market[0]["capabilities"] == ["Skills"]
        assert market[0]["marketplace"] == "team-market"
    finally:
        service.close()


def test_mcp_json_batch_is_atomic_and_preserves_environment_and_enablement(tmp_path):
    import pytest

    service = DesktopService(tmp_path / "data")
    try:
        service.invoke(
            "saveMcpJson",
            {
                "config": {
                    "mcpServers": {
                        "qa": {
                            "type": "stdio",
                            "command": "npx",
                            "args": ["-y", "fixture"],
                            "env": {"QA_TOKEN": "${QA_TOKEN}"},
                        },
                        "remote": {
                            "type": "http",
                            "url": "https://example.com/mcp",
                            "headers": {"Authorization": "Bearer ${QA_REMOTE_TOKEN}"},
                        },
                    }
                }
            },
        )
        entries = service.store.get("settings", "mcp")
        assert entries["qa"]["config"]["env_from"] == ["QA_TOKEN"]
        assert entries["remote"]["config"]["bearer_token_env"] == "QA_REMOTE_TOKEN"
        service.invoke("mcpConfigUpsert", {"scope": "user", "name": "qa", "enabled": True})
        config = service.invoke("mcpConfigList", {})["global"][0]["config"]
        service.invoke("saveMcpJson", {"config": {"mcpServers": {"qa": config}}})
        assert service.store.get("settings", "mcp")["qa"]["enabled"]
        before = service.store.get("settings", "mcp")
        with pytest.raises(ValueError):
            service.invoke(
                "saveMcpJson", {"config": {"mcpServers": {"new": {"command": "npx"}, "invalid": {"url": "bad"}}}}
            )
        assert service.store.get("settings", "mcp") == before
    finally:
        service.close()


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
            "baseUrl": "https://example.com/v1",
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
                    "commandShell": "system",
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
