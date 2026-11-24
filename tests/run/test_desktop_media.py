"""Lossless screenshot storage, restart, backup restoration and concurrent-edit fences."""

import base64
import json
import random
import sqlite3
import struct
import zlib
from uuid import uuid4

import pytest

from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore


def screenshot_png() -> bytes:
    """Produce a valid deterministic RGB PNG with enough detail to exercise binary deduplication."""

    def chunk(name, content):
        return struct.pack(">I", len(content)) + name + content + struct.pack(">I", zlib.crc32(name + content))

    pixels = random.Random(1122).randbytes(64 * 64 * 3)
    scanlines = b"".join(b"\0" + pixels[row * 192 : (row + 1) * 192] for row in range(64))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def test_screenshot_compaction_is_lossless_after_restart_and_restore_does_not_overwrite_new_messages(tmp_path):
    state = tmp_path / "state"
    service = DesktopService(state)
    try:
        meta = service.invoke("createSession", {"options": {"cwd": str(tmp_path)}})
        key = meta["sessionId"]
        encoded = base64.b64encode(screenshot_png()).decode()
        original = service.sessions.get(key)
        original["selections"]["literal"] = {"__vera_image_blob_v1__": "user-text", "prefix": "unchanged"}
        original["messages"] = [
            {
                "kind": "user",
                "id": "user",
                "text": "Inspect this screenshot",
                "images": [{"data": encoded, "mimeType": "image/png"}],
                "tools": [],
                "timestamp": 1,
            }
        ]
        original["runtimeMessages"] = [
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}}],
            }
        ]
        service.save_session(original)
        args = {"sessionFile": meta["sessionFile"]}
        preview = service.invoke("startSessionMediaPreview", args)["result"]
        assert preview["uniqueImages"] == 1 and preview["projectedFileBytes"] < preview["fileBytes"]
        request = uuid4().hex
        job = service.invoke(
            "startSessionMediaCompaction",
            args | {"requestId": request, "expectedHash": preview["sourceHash"], "confirmed": True},
        )
        assert job["transaction"]["phase"] == "complete"
        assert service.sessions.get(key) == original
        with sqlite3.connect(service.store.path) as db:
            assert db.execute("SELECT count(*) FROM image_blobs WHERE owner=?", (key,)).fetchone()[0] == 1
            assert (
                encoded
                not in db.execute("SELECT value FROM documents WHERE kind='session' AND id=?", (key,)).fetchone()[0]
            )
        assert encoded not in open(meta["sessionFile"], encoding="utf-8").read()
        service.close()
        service = DesktopService(state)
        assert service.sessions.get(key) == original
        closed = service.sessions.get(key)
        closed["meta"]["active"] = False
        service.save_session(closed)
        original["meta"]["active"] = False
        restored = service.invoke(
            "startSessionMediaRestore", {"requestId": uuid4().hex, "compactionRequestId": request, "confirmed": True}
        )
        assert restored["status"] == "completed" and service.sessions.get(key) == original
        assert json.loads(open(restored["transaction"]["backup"], encoding="utf-8").read()) == original
        request = uuid4().hex
        preview = service.invoke("startSessionMediaPreview", args)["result"]
        service.invoke(
            "startSessionMediaCompaction",
            args | {"requestId": request, "expectedHash": preview["sourceHash"], "confirmed": True},
        )
        changed = service.sessions.get(key)
        changed["messages"].append({"kind": "user", "text": "Keep this later message", "images": []})
        service.save_session(changed)
        with pytest.raises(ValueError, match="后续对话"):
            service.invoke(
                "startSessionMediaRestore",
                {"requestId": uuid4().hex, "compactionRequestId": request, "confirmed": True},
            )
        assert service.sessions.get(key) == changed
        with pytest.raises(ValueError, match="已有的会话"):
            service.invoke("startSessionMediaPreview", {"sessionFile": str(tmp_path / "other.json")})
    finally:
        service.close()


# Value: protects=missing media cannot resolve a blob owned by another session;
# fails_when=decoding silently drops missing media or ignores the owner boundary;
# why_new=the compaction test only reads existing blobs owned by the same session; seam=none;
# no_claim=repair of corrupt stores; SQLite edits model missing or misowned media.
@pytest.mark.parametrize("other_owner", [None, "other-session"])
def test_missing_session_image_fails_even_when_another_owner_has_the_blob(tmp_path, other_owner):
    store = DesktopStore(tmp_path)
    original = store.create_session({"cwd": str(tmp_path)})
    key = original["meta"]["sessionId"]
    original["messages"] = [
        {"images": [{"mimeType": "image/png", "data": base64.b64encode(screenshot_png()).decode()}]}
    ]
    store.image_layout(key, original, enabled=True)
    assert store.get("session", key) == original
    with sqlite3.connect(store.path) as db:
        if other_owner is None:
            db.execute("DELETE FROM image_blobs WHERE owner=?", (key,))
        else:
            db.execute("UPDATE image_blobs SET owner=? WHERE owner=?", (other_owner, key))
    with pytest.raises(ValueError, match="会话图片缺失"):
        store.get("session", key)
    with pytest.raises(ValueError, match="会话图片缺失"):
        store.list("session")


# Value: protects=invalid typed image payloads survive storage unchanged without creating blobs;
# fails_when=encoding drops malformed base64 or replaces it with a blob reference;
# why_new=existing media fixtures contain only valid base64; seam=none;
# no_claim=image format validation; this checks lossless handling of malformed base64.
def test_malformed_base64_is_preserved_in_attachment_and_runtime_image_fields(tmp_path):
    store = DesktopStore(tmp_path)
    original = store.create_session({"cwd": str(tmp_path)})
    key = original["meta"]["sessionId"]
    original["messages"] = [{"images": [{"mimeType": "image/png", "data": "not valid base64!"}]}]
    original["runtimeMessages"] = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,invalid!"}}]}
    ]
    store.image_layout(key, original, enabled=True)
    assert store.get("session", key) == original
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT count(*) FROM image_blobs WHERE owner=?", (key,)).fetchone()[0] == 0
        assert (
            json.loads(db.execute("SELECT value FROM documents WHERE kind='session' AND id=?", (key,)).fetchone()[0])
            == original
        )
