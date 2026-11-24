"""Regressions for OCR media restore, storage references and session configuration boundaries."""

import base64
import sqlite3
from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest

from vera.desktop.media_codec import MARKER
from vera.desktop.media_maintenance import fingerprint
from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore


@pytest.fixture
def service(tmp_path):
    """Keep tests local: no worker or provider request is started by the fixture."""
    instance = DesktopService(tmp_path / "state")
    try:
        yield instance
    finally:
        instance.close()


def screenshot(value: bytes) -> dict:
    """Use distinct binary payloads to observe owner-scoped blob retention."""
    return {"mimeType": "image/png", "data": base64.b64encode(value).decode()}


def session_with_images(service, workspace):
    """Store two screenshots in both display and model history for recall/compaction tests."""
    meta = service.invoke("createSession", {"options": {"cwd": str(workspace)}})
    value = service.sessions.get(meta["sessionId"])
    value["messages"] = [
        {
            "kind": "user",
            "entryId": f"entry-{index}",
            "text": f"image-{index}",
            "images": [screenshot(payload)],
            "runtimeIndex": index,
        }
        for index, payload in enumerate((b"keep screenshot", b"discard screenshot"))
    ]
    value["runtimeMessages"] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + row["images"][0]["data"]}}
            ],
        }
        for row in value["messages"]
    ]
    service.save_session(value)
    return value


@pytest.mark.parametrize("damage", ["missing", "invalid-json", "invalid-encoding", "invalid-meta"])
def test_restore_unreadable_backup_keeps_session_and_published_transaction(service, tmp_path, damage):
    original = session_with_images(service, tmp_path)
    key = original["meta"]["sessionId"]
    request = uuid4().hex
    service.invoke(
        "startSessionMediaCompaction",
        {
            "sessionFile": original["meta"]["sessionFile"],
            "requestId": request,
            "expectedHash": fingerprint(original),
            "confirmed": True,
        },
    )
    backup = service.store.directory / "media-backups" / f"{request}.json"
    if damage == "missing":
        backup.unlink()
    elif damage == "invalid-json":
        backup.write_text("{broken", encoding="utf-8")
    elif damage == "invalid-encoding":
        backup.write_bytes(b"\xff")
    else:
        backup.write_text('{"meta": []}', encoding="utf-8")
    transaction = service.store.get("media-latest", key)
    restore_request = uuid4().hex
    with pytest.raises(ValueError, match="截图整理备份.*已保留当前会话"):
        service.invoke(
            "startSessionMediaRestore",
            {"compactionRequestId": request, "requestId": restore_request, "confirmed": True},
        )
    assert service.sessions.get(key) == original
    assert service.store.get("media-latest", key) == transaction
    assert service.store.get("media-transaction", restore_request) is None


@pytest.mark.parametrize("image_field", ["attachment", "runtime"])
@pytest.mark.parametrize("damage", ["missing-prefix", "extra-key", "invalid-digest", "invalid-prefix"])
def test_malformed_image_reference_fails_at_storage_boundary(tmp_path, image_field, damage):
    store = DesktopStore(tmp_path)
    value = store.create_session({"cwd": str(tmp_path)})
    reference = {MARKER: "digest", "prefix": ""}
    if damage == "missing-prefix":
        reference.pop("prefix")
    elif damage == "extra-key":
        reference["extra"] = True
    elif damage == "invalid-digest":
        reference[MARKER] = []
    else:
        reference["prefix"] = None
    value["messages"] = [
        {"images": [{"mimeType": "image/png", "data": reference}]}
        if image_field == "attachment"
        else {"role": "user", "content": [{"type": "image_url", "image_url": {"url": reference}}]}
    ]
    key = value["meta"]["sessionId"]
    store.save("session", key, value)
    with pytest.raises(ValueError, match="图片引用格式无效"):
        store.get("session", key)


def test_recall_prunes_only_discarded_owner_blobs_and_preserves_existing_references(service, tmp_path):
    original = session_with_images(service, tmp_path)
    key = original["meta"]["sessionId"]
    sibling = session_with_images(service, tmp_path)
    sibling_key = sibling["meta"]["sessionId"]
    for owner, value in ((key, original), (sibling_key, sibling)):
        service.store.image_layout(owner, value, enabled=True)
    # A metadata-only reader can save encoded references without re-inserting blob bytes.
    encoded = next(
        value for value in service.store.list("session", decode_media=False) if value["meta"]["sessionId"] == key
    )
    service.store.save("session", key, encoded)
    assert service.sessions.get(key) == original
    recalled = service.invoke("recallMessage", {"sessionId": key, "ref": {"entryId": "entry-1"}})
    assert recalled["images"] == original["messages"][1]["images"]
    kept = service.sessions.get(key)
    assert kept["messages"] == original["messages"][:1]
    assert kept["runtimeMessages"] == original["runtimeMessages"][:1]
    with sqlite3.connect(service.store.path) as db:
        assert db.execute("SELECT count(*) FROM image_blobs WHERE owner=?", (key,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM image_blobs WHERE owner=?", (sibling_key,)).fetchone()[0] == 2
    assert service.sessions.get(sibling_key) == sibling
    assert DesktopStore(service.store.directory).get("session", key) == kept


def test_catalog_reads_once_without_decoding_broken_session_images(service, tmp_path, monkeypatch):
    damaged = session_with_images(service, tmp_path)
    healthy = session_with_images(service, tmp_path)
    key = damaged["meta"]["sessionId"]
    service.store.image_layout(key, damaged, enabled=True)
    with sqlite3.connect(service.store.path) as db:
        db.execute("DELETE FROM image_blobs WHERE owner=?", (key,))
    real_list = service.store.list
    catalog_reads = []

    def metadata_only(kind, **options):
        catalog_reads.append((kind, options))
        assert options == {"decode_media": False}
        return real_list(kind, **options)

    monkeypatch.setattr(service.store, "list", metadata_only)
    references = [{"sessionId": key}, {"sessionFile": healthy["meta"]["sessionFile"]}, {"sessionId": "missing"}]
    results = service.invoke("verifySessionCatalog", {"references": references})
    assert [row["status"] for row in results] == ["present", "present", "missing"]
    assert catalog_reads == [("session", {"decode_media": False})]
    assert len(service.invoke("listAllSessions")) == 2
    assert len(service.invoke("getLoadedSessions")) == 2
    assert service.invoke("openSession", {"filePath": healthy["meta"]["sessionFile"]}) == healthy["meta"]
    assert service.sessions.get(healthy["meta"]["sessionId"]) == healthy
    with pytest.raises(ValueError, match="会话图片缺失"):
        service.sessions.get(key)


@pytest.mark.parametrize("options", [{"toolCallLimit": 10001}, {"toolCallLimit": 0}, {"topK": 0}, {"unknown": 1}])
def test_session_option_save_rejects_invalid_options_without_persisting_partial_changes(service, tmp_path, options):
    meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
    key = meta["sessionId"]
    before = service.sessions.get(key)
    with pytest.raises(ValueError):
        service.invoke(
            "setSessionSelections",
            {"sessionId": key, "modelOptions": options, "permissionPolicy": "human", "selections": {"runMode": "goal"}},
        )
    assert service.sessions.get(key) == before


def test_saved_session_option_boundaries_match_execution_config_and_legacy_invalid_values_are_actionable(
    service, tmp_path
):
    meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
    key = meta["sessionId"]
    service.invoke(
        "setSessionSelections",
        {
            "sessionId": key,
            "permissionPolicy": "human",
            "modelOptions": {
                "toolCallLimit": "10000",
                "temperature": 0,
                "topP": 0,
                "topK": "",
                "reasoningParameter": "reasoning.effort",
            },
        },
    )
    config = service.sessions.config(service.sessions.get(key))
    assert config["agent"]["desktop_tool_call_limit"] == 10000
    assert config["model"]["model_kwargs"] == {"temperature": 0, "top_p": 0}
    legacy = service.sessions.get(key)
    legacy["modelOptions"] = {"toolCallLimit": 50000}
    service.store.save("session", key, legacy)
    with pytest.raises(ValueError, match="重新保存有效的模型选项"):
        service.sessions.config(service.sessions.get(key))


@pytest.mark.parametrize("mode", ["human", "unselected"])
def test_image_rejection_precedes_terminal_and_worker_in_manual_or_unselected_session(
    service, tmp_path, monkeypatch, mode
):
    meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
    key = meta["sessionId"]
    value = service.sessions.get(key)
    if mode == "human":
        value["permissionPolicy"] = "human"
        value["meta"]["model"] = {"provider": "removed", "modelId": "removed"}
    else:
        service.sessions.base_config = {"agent": {}, "model": {"model_name": "configured-base-model"}}
    service.store.save("session", key, value)
    terminal = Mock(side_effect=AssertionError("terminal must not process images"))
    monkeypatch.setattr(service.sessions, "terminal", terminal)
    with pytest.raises(ValueError, match="图片"):
        service.invoke("prompt", {"sessionId": key, "text": "echo command", "images": [screenshot(b"attachment")]})
    terminal.assert_not_called()
    assert service.sessions.get(key) == value
    assert not service.sessions.running
    assert not (service.store.directory / "artifacts").exists()


def test_selected_provider_rejects_unsupported_reasoning_but_human_does_not_load_provider(
    service, tmp_path, monkeypatch
):
    service.providers.configure(
        {
            "id": "local",
            "api": "openai-completions",
            "baseUrl": "http://127.0.0.1:1/v1",
            "models": [
                {"id": "reasoner", "reasoning": True, "advanced": {"reasoningValues": ["default", "off", "low"]}}
            ],
        }
    )
    meta = service.invoke(
        "createSession",
        {"options": {"cwd": str(tmp_path), "provider": "local", "modelId": "reasoner", "thinkingLevel": "high"}},
    )
    value = service.sessions.get(meta["sessionId"])
    with pytest.raises(ValueError, match="不支持此思考强度"):
        service.sessions.config(value)
    manual = deepcopy(value) | {"permissionPolicy": "human"}
    monkeypatch.setattr(
        service.providers, "definition", Mock(side_effect=AssertionError("manual must not read provider"))
    )
    config = service.sessions.config(manual)
    assert config["model"]["model_class"] == "deterministic"
    assert config["agent"]["mode"] == "human"
