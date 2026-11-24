"""Exercise concrete OCR fixes with local stores and bounded runtime substitutes."""

import hashlib
import subprocess
import time
from types import SimpleNamespace

import pytest

from vera.channels.config import InboundMessage
from vera.channels.credentials import CredentialStore
from vera.channels.store import ChannelStore
from vera.desktop import prompts, shells
from vera.desktop.performance import PerformanceStats
from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore
from vera.desktop.web import WebSettings
from vera.utils.serialize import strip_sensitive


@pytest.mark.parametrize(
    ("template", "content", "expected"),
    [
        ("{{task}}", "Keep this", "Keep this"),
        ("Task: {{task}}", "Task: Keep this", "Keep this"),
        ("Task: {{task}} done", "Task: Keep this done", "Keep this"),
        ("literal", "literal", "literal"),
    ],
)
def test_legacy_history_preserves_task_with_empty_suffix(monkeypatch, template, content, expected):
    monkeypatch.setattr(prompts, "get_config_from_spec", lambda _: {"agent": {"instance_template": template}})
    original = [{"role": "user", "content": content}]
    assert prompts.refresh_legacy_history(original, {}) == [{"role": "user", "content": expected}]
    assert original[0]["content"] == content


def test_performance_accepts_all_time_empty_filters(tmp_path):
    stats = PerformanceStats(DesktopStore(tmp_path))
    assert stats.query([], [])["tasks"] == 0


def windows_shell_fixture(monkeypatch):
    """Use deterministic local probe results on every CI operating system."""
    monkeypatch.setattr(shells, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(shells, "_cached", (None, []))
    monkeypatch.setattr(shells.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(shells, "find_git_bash", lambda: None)
    monkeypatch.setattr(shells.shutil, "which", lambda _: None)


def test_shell_first_probe_never_returns_empty_cache(monkeypatch):
    windows_shell_fixture(monkeypatch)
    monkeypatch.setattr(shells.time, "monotonic", lambda: 1.0)
    assert shells.command_shells()[0]["id"] == "system"


def test_removed_git_bash_cannot_use_cached_executable(monkeypatch):
    windows_shell_fixture(monkeypatch)
    monkeypatch.setattr(shells, "_cached", (time.monotonic(), [{"id": "git-bash", "command": ["missing-bash"]}]))
    with pytest.raises(ValueError, match="Bash"):
        shells.shell_command("git-bash")


@pytest.mark.parametrize("failure", ["override", "wsl"])
def test_shell_detection_degrades_when_optional_probe_fails(monkeypatch, failure):
    windows_shell_fixture(monkeypatch)

    def fail_override():
        raise FileNotFoundError("removed override")

    if failure == "override":
        monkeypatch.setattr(shells, "find_git_bash", fail_override)
    else:
        monkeypatch.setattr(shells.shutil, "which", lambda name: "wsl" if name == "wsl" else None)

        def fail_probe(*args, **kwargs):
            raise subprocess.TimeoutExpired("wsl", 5)

        monkeypatch.setattr(shells.subprocess, "run", fail_probe)
    assert shells.command_shells(refresh=True) == [
        {"id": "system", "label": "系统默认（自动选择 Bash）", "command": []}
    ]


def test_wsl_bom_is_not_part_of_distribution_name(monkeypatch):
    windows_shell_fixture(monkeypatch)
    monkeypatch.setattr(shells.shutil, "which", lambda name: "wsl" if name == "wsl" else None)

    def probe(command, **kwargs):
        if "--list" in command:
            return subprocess.CompletedProcess(command, 0, "\ufeffUbuntu\r\n".encode("utf-16-le"))
        assert command[2] == "Ubuntu"
        return subprocess.CompletedProcess(command, 0, b"VERA_BASH_READY")

    monkeypatch.setattr(shells.subprocess, "run", probe)
    assert shells.command_shells(refresh=True)[1]["id"] == "wsl:Ubuntu"


def test_sensitive_key_variants_are_not_persisted():
    value = {
        "private_key": "fixture",
        "aws_secret_key": "fixture",
        "credentials": {"opaque": "fixture"},
        "nested": {"passwd": "fixture", "private_key_id": "public-id", "model_name": "fixture"},
    }
    assert strip_sensitive(value) == {"nested": {"private_key_id": "public-id", "model_name": "fixture"}}


def test_saved_searxng_url_survives_blank_input_and_can_be_removed(tmp_path):
    settings = WebSettings(DesktopStore(tmp_path))
    settings.save({"provider": "searxng", "enabled": False, "readPages": False, "searxngUrl": "http://localhost:8080"})
    assert settings.save({"provider": "searxng", "enabled": False})["searxngUrl"] == "http://localhost:8080"
    assert settings.save({"provider": "searxng", "enabled": False, "removeKey": True})["searxngUrl"] == ""
    assert "searxng" not in settings.credentials()


def test_corrupt_web_vault_can_be_replaced_without_losing_settings_panel(tmp_path):
    settings = WebSettings(DesktopStore(tmp_path))
    settings.vault.directory.mkdir()
    settings.vault._path("desktop-web").write_text("invalid-json", encoding="utf-8")
    assert settings.credentials() == {}
    settings.save({"provider": "searxng", "enabled": False, "searxngUrl": "http://localhost:8080"})
    assert settings.credentials()["searxng"] == "http://localhost:8080"


def test_malformed_searxng_authority_has_actionable_validation_error(tmp_path):
    settings = WebSettings(DesktopStore(tmp_path))
    with pytest.raises(ValueError, match="SearXNG"):
        settings.save({"provider": "searxng", "enabled": False, "searxngUrl": "http://[::1"})


def test_deferred_queue_keeps_control_command_available_at_capacity(tmp_path):
    store = ChannelStore(tmp_path, defer_dispatch=True)

    def message(number, text):
        return InboundMessage(
            account="fixture", channel="weixin", message_id=str(number), user="owner", conversation="chat", text=text
        )

    store.accept([message(number, "Task") for number in range(100)])
    store.accept([message(100, "/cancel")])
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 101


def test_project_deletion_ignores_view_activation_but_reports_partial_failure(tmp_path, monkeypatch):
    service = DesktopService(tmp_path / "state")
    try:
        first = service.store.create_session({"cwd": str(tmp_path)})
        second = service.store.create_session({"cwd": str(tmp_path)})
        args = {"cwd": str(tmp_path.resolve())}
        token = service.project_deletion.invoke("previewSessionProjectDeletion", args)["token"]
        first["meta"]["active"] = False
        service.store.save("session", first["meta"]["sessionId"], first)
        original = service.store.delete

        def delete(kind, key):
            if key == first["meta"]["sessionId"]:
                raise PermissionError("fixture write denied")
            original(kind, key)

        monkeypatch.setattr(service.store, "delete", delete)
        events = []
        monkeypatch.setattr(service.events, "emit", lambda *event: events.append(event))
        result = service.project_deletion.invoke("deleteSessionProject", args | {"token": token})
        assert result["deleted"] == [second["meta"]["sessionId"]]
        assert result["failed"][0]["sessionId"] == first["meta"]["sessionId"]
        assert events[0][0] == "onSessionCatalogChanged"
    finally:
        service.close()


def test_feishu_pairing_worker_signals_the_host_selected_stop_file(tmp_path, monkeypatch):
    from vera.channels import feishu, worker

    vault = CredentialStore(tmp_path)
    stop = tmp_path / "desktop-custom.stop"
    vault.save(
        "pairing-fixture",
        {
            "account": "fixture",
            "settings": {"channel": "feishu"},
            "credentials": {},
            "code_hash": hashlib.sha256(b"fixture-code").hexdigest(),
            "expires": time.time() + 30,
            "stop_path": str(stop),
        },
    )

    class Listener:
        def __init__(self, *args):
            pass

        def listen(self, account, accept, status):
            accept(
                InboundMessage(
                    account=account,
                    channel="feishu",
                    message_id="fixture",
                    user="owner",
                    conversation="chat",
                    text="/pair fixture-code",
                )
            )

    monkeypatch.setattr(feishu, "FeishuClient", Listener)
    worker.pair_feishu(tmp_path, "fixture")
    assert stop.exists()
    assert vault.load("paired-fixture")["allowed_users"] == ["owner"]


def test_plugin_market_uses_returned_identity_and_rejects_stale_selection(tmp_path, monkeypatch):
    service = DesktopService(tmp_path / "state")
    catalogs = {}

    def add(source):
        assert source == "anthropics/claude-plugins-official"
        catalogs["declared-name"] = {"presentation_version": 1, "plugins": {}}
        return {"name": "declared-name"}

    try:
        monkeypatch.setattr(
            service.capabilities, "plugins", SimpleNamespace(list_marketplaces=lambda: catalogs, add_marketplace=add)
        )
        assert service.invoke("pluginMarket", {"source": "anthropic"}) == []
        with pytest.raises(ValueError, match="仓库"):
            service.invoke("pluginMarket", {"source": "removed-name"})
    finally:
        service.close()


def test_feishu_pairing_host_publishes_custom_completion_path(tmp_path, monkeypatch):
    from vera.channels import feishu
    from vera.channels.config import ChannelConfig
    from vera.evolution import process

    config = ChannelConfig(
        workspace=tmp_path, state_directory=tmp_path / "state", accounts={"fixture": {"channel": "feishu"}}
    )

    class Client:
        app_id = "fixture"
        secret = "fixture"

        def __init__(self, *args):
            pass

        def check(self):
            pass

    stop = tmp_path / "custom.stop"

    def run(command, **kwargs):
        nonce = command[-1]
        vault = CredentialStore(config.state_directory)
        assert vault.load(f"pairing-{nonce}")["stop_path"] == str(stop.resolve())
        vault.save(f"paired-{nonce}", {"allowed_users": ["owner"]})
        return {"status": "cancelled"}

    monkeypatch.setattr(feishu, "FeishuClient", Client)
    monkeypatch.setattr(process, "run_process", run)
    assert feishu.pair_account(config, "fixture", lambda _: None, credentials={}, cancel_path=stop)["paired"]
