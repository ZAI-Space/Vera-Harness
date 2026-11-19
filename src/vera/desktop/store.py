"""Persist desktop metadata separately from durable runtime receipts and secrets."""

import json
import sqlite3
import threading
import time
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from uuid import uuid4


class DesktopStore:
    """Atomic JSON documents in SQLite; callers receive detached copies.

    Session exports are accepted only after matching the authoritative catalog.
    Credentials belong in the separate private provider store, never session data.
    """

    def __init__(self, directory: Path):
        self.directory = directory.expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "desktop.sqlite3"
        self.lock = threading.RLock()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS documents (kind TEXT, id TEXT, value TEXT, PRIMARY KEY(kind,id))")

    def get(self, kind: str, key: str, default=None):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT value FROM documents WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else deepcopy(default)

    def save(self, kind: str, key: str, value) -> None:
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?)", (kind, key, json.dumps(value)))

    def delete(self, kind: str, key: str) -> None:
        with self.lock, closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM documents WHERE kind=? AND id=?", (kind, key))

    def list(self, kind: str) -> list:
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            return [json.loads(row[0]) for row in db.execute("SELECT value FROM documents WHERE kind=?", (kind,))]

    def create_session(self, options: dict) -> dict:
        """Bind a new conversation to a real workspace; no model request is made."""
        workspace = Path(options["cwd"]).expanduser().resolve(strict=True)
        if not workspace.is_dir():
            raise ValueError("Choose a project directory.")
        key, now = uuid4().hex, int(time.time() * 1000)
        model = (
            {"provider": options["provider"], "modelId": options["modelId"]}
            if options.get("provider") and options.get("modelId")
            else None
        )
        value = {
            "meta": {
                "sessionId": key,
                "sessionFile": str(self.directory / "sessions" / f"{key}.json"),
                "cwd": str(workspace),
                "active": True,
                "messageCount": 0,
                "createdAt": now,
                "modifiedAt": now,
                "model": model,
                "thinkingLevel": options.get("thinkingLevel", "off"),
            },
            "messages": [],
            "runtimeMessages": [],
            "sequence": 0,
            "permissionMode": "default",
            "selections": {},
            "stats": {"inputTokens": 0, "outputTokens": 0, "cost": 0},
        }
        self.save("session", key, value)
        self.checkpoint_session(value)
        return value

    def checkpoint_session(self, value: dict) -> None:
        """Export a safe display snapshot; SQLite remains the authoritative catalog."""
        from vera.evolution.process import write_json

        path = self.directory / "sessions" / (value["meta"]["sessionId"] + ".json")
        path.parent.mkdir(exist_ok=True)
        write_json(path, {"meta": value["meta"], "messages": value["messages"]})
