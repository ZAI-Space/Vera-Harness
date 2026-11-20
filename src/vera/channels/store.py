"""Durable channel inbox/outbox, scoped conversation history and crash reconciliation."""

import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from vera.channels.config import ChannelError, InboundMessage
from vera.channels.credentials import private_directory

_SCHEMA = (
    "CREATE TABLE sessions (id TEXT PRIMARY KEY, epoch INTEGER NOT NULL DEFAULT 0)",
    """CREATE TABLE messages (id TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL,
        epoch INTEGER NOT NULL, status TEXT NOT NULL, run_id TEXT NOT NULL, created REAL NOT NULL,
        cancel INTEGER NOT NULL DEFAULT 0, progress TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX message_queue ON messages(status, created)",
    """CREATE TABLE outbox (id TEXT PRIMARY KEY, account TEXT NOT NULL, payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)""",
    "CREATE TABLE cursors (account TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE connections (account TEXT PRIMARY KEY, status TEXT NOT NULL, updated REAL NOT NULL)",
)


def chunks(text: str, size: int = 2000) -> list[str]:
    """Split replies by UTF-8 bytes without breaking Unicode code points."""
    result, current, length = [], [], 0
    for character in text[:32_000]:
        encoded = len(character.encode("utf-8"))
        if length + encoded > size:
            result.append("".join(current))
            current, length = [], 0
        current.append(character)
        length += encoded
    if current:
        result.append("".join(current))
    return result or ["（无文本结果）"]


class ChannelStore:
    """One private SQLite journal; every accepted event is persisted before it is acknowledged."""

    def __init__(self, directory: Path):
        self.directory = private_directory(directory)
        self.path = directory / "channels.sqlite3"
        with self.connect(write=False) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            with self.connect() as db:
                # Another process may have initialized the journal while we waited for the writer lock.
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0:
                    for statement in _SCHEMA:
                        db.execute(statement)
                    db.execute("PRAGMA user_version = 1")
                    version = 1
        if version != 1:
            raise ChannelError("Unsupported channel database schema.")
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connect(self, *, write: bool = True):
        """Commit or roll back a short transaction; reads do not reserve the writer lock.

        The default serializes writes. Pass ``write=False`` for a committed read snapshot.
        SQLite errors propagate; callers must not perform network calls inside a transaction.
        """
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    def _reply(self, db, message: InboundMessage, text: str, label: str) -> None:
        parts = chunks(text)
        for index, part in enumerate(parts):
            text = f"[{index + 1}/{len(parts)}] {part}" if len(parts) > 1 else part
            key = uuid5(NAMESPACE_URL, f"{message.key}/{label}/{index}").hex
            db.execute(
                "INSERT OR IGNORE INTO outbox(id, account, payload, created) VALUES (?, ?, ?, ?)",
                (key, message.account, json.dumps({"message": message.model_dump(), "text": text}), time.time()),
            )

    def accept(self, messages: list[InboundMessage], *, account: str = "", cursor: str | None = None) -> None:
        """Deduplicate authorized events and advance a polling cursor in the same transaction."""
        with self.connect() as db:
            for message in messages:
                if db.execute("SELECT 1 FROM messages WHERE id = ?", (message.key,)).fetchone():
                    continue
                db.execute("INSERT OR IGNORE INTO sessions(id) VALUES (?)", (message.session_id,))
                epoch = db.execute("SELECT epoch FROM sessions WHERE id = ?", (message.session_id,)).fetchone()[0]
                command = message.text.strip()
                status = "command" if command.startswith("/") or not command else "queued"
                if (
                    status == "queued"
                    and db.execute("SELECT COUNT(*) FROM messages WHERE status = 'queued'").fetchone()[0] >= 100
                ):
                    raise ChannelError("Inbound queue is full; cursor not advanced.")
                db.execute(
                    "INSERT INTO messages(id, session, payload, epoch, status, run_id, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        message.key,
                        message.session_id,
                        message.model_dump_json(),
                        epoch,
                        status,
                        uuid4().hex,
                        time.time(),
                    ),
                )
                if status == "command":
                    self._command(db, message, command)
            if cursor:
                db.execute("INSERT OR REPLACE INTO cursors(account, value) VALUES (?, ?)", (account, cursor))

    def _command(self, db, message: InboundMessage, command: str) -> None:
        active = db.execute(
            "SELECT * FROM messages WHERE session = ? AND status IN ('queued', 'running') ORDER BY created DESC",
            (message.session_id,),
        ).fetchall()
        if command == "/cancel":
            db.execute(
                "UPDATE messages SET cancel = 1 WHERE session = ? AND status IN ('queued', 'running')",
                (message.session_id,),
            )
            db.execute(
                "UPDATE messages SET status = 'cancelled' WHERE session = ? AND status = 'queued'",
                (message.session_id,),
            )
            text = "已请求取消本会话的任务。正在执行的工具可能需要等待返回。"
        elif command == "/new":
            if active:
                text = "请先 /cancel，待当前任务结束后再 /new。"
            else:
                db.execute("UPDATE sessions SET epoch = epoch + 1 WHERE id = ?", (message.session_id,))
                text = "已开始新会话；历史任务记录保留。"
        elif command == "/status":
            latest = db.execute(
                "SELECT status, progress, run_id FROM messages WHERE session = ? AND status != 'command' ORDER BY created DESC LIMIT 1",
                (message.session_id,),
            ).fetchone()
            text = (
                f"状态：{latest['status']}\n{latest['progress']}\n任务：{latest['run_id']}"
                if latest
                else "本会话还没有任务。"
            )
        else:
            text = "发送文字即可执行任务。/status 查询状态，/cancel 取消任务，/new 清空后续会话上下文，/help 查看帮助。"
            if not command:
                text = "当前仅处理文字和已有语音转写文本。\n" + text
        self._reply(db, message, text, "command")

    def cursor(self, account: str) -> str:
        """Return the last committed Weixin cursor."""
        with self.connect(write=False) as db:
            row = db.execute("SELECT value FROM cursors WHERE account = ?", (account,)).fetchone()
            return row[0] if row else ""

    def claim(self) -> dict | None:
        """Atomically claim the oldest queued task; one gateway supervises one worker at a time."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM messages WHERE status = 'queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE messages SET status = 'running' WHERE id = ?", (row["id"],))
                message = InboundMessage.model_validate_json(row["payload"])
                self._reply(db, message, f"任务已开始：{row['run_id']}。可用 /status 查询或 /cancel 取消。", "start")
            return dict(row) | {"status": "running"} if row else None

    def get(self, key: str) -> dict:
        """Read a task for the worker/supervisor; IDs are internal hashes, never chat-supplied run IDs."""
        with self.connect(write=False) as db:
            row = db.execute("SELECT * FROM messages WHERE id = ?", (key,)).fetchone()
            if row is None:
                raise ChannelError("Unknown channel message.")
            return dict(row)

    def history(self, key: str) -> str:
        """Bound prior completed turns to this session and epoch; omit tool transcripts and secrets."""
        row = self.get(key)
        with self.connect(write=False) as db:
            previous = db.execute(
                "SELECT payload, result FROM messages WHERE session = ? AND epoch = ? AND status = 'completed' AND rowid < (SELECT rowid FROM messages WHERE id = ?) ORDER BY rowid DESC LIMIT 6",
                (row["session"], row["epoch"], key),
            ).fetchall()
        turns = [
            {"user": json.loads(entry["payload"])["text"][:8000], "assistant": entry["result"][:4000]}
            for entry in reversed(previous)
        ]
        while turns and len(json.dumps(turns, ensure_ascii=False)) > 24_000:
            turns.pop(0)
        return json.dumps(turns, ensure_ascii=False)

    def progress(self, key: str, text: str) -> None:
        """Persist compact phase/counter information without recording model reasoning in chat."""
        with self.connect() as db:
            db.execute("UPDATE messages SET progress = ? WHERE id = ?", (text[:300], key))

    def finish(self, key: str, status: str, result: str) -> None:
        """Commit a terminal result and durable reply atomically; repeat completion is harmless."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM messages WHERE id = ?", (key,)).fetchone()
            if row["status"] != "running":
                return
            db.execute("UPDATE messages SET status = ?, result = ? WHERE id = ?", (status, result[:32_000], key))
            message = InboundMessage.model_validate_json(row["payload"])
            self._reply(db, message, f"[{status}]\n{result}", "result")

    def reconcile(self) -> None:
        """Mark abandoned runs/replies uncertain on startup; never replay possible side effects."""
        with self.connect() as db:
            rows = db.execute("SELECT id FROM messages WHERE status = 'running'").fetchall()
            db.execute("UPDATE outbox SET status = 'unknown' WHERE status = 'sending'")
        for row in rows:
            self.finish(
                row["id"], "interrupted", "进程中断；任务未自动重放。请检查本地任务和工具记录后再决定是否重新发起。"
            )

    def pending_reply(self, accounts: set[str]) -> dict | None:
        """Claim one outbound fragment; uncertainty is retained instead of silently resending."""
        if not accounts:
            return None
        with self.connect() as db:
            placeholders = ",".join("?" for _ in accounts)
            row = db.execute(
                f"SELECT * FROM outbox WHERE status = 'pending' AND account IN ({placeholders}) ORDER BY created LIMIT 1",
                tuple(accounts),
            ).fetchone()
            if row:
                db.execute("UPDATE outbox SET status = 'sending', attempts = attempts + 1 WHERE id = ?", (row["id"],))
            return dict(row) if row else None

    def sent(self, key: str, status: str) -> None:
        """Record sent, definite failure or unknown delivery; only explicit operator retry requeues unknowns."""
        if status not in {"sent", "failed", "unknown"}:
            raise ChannelError("Invalid delivery status.")
        with self.connect() as db:
            db.execute("UPDATE outbox SET status = ? WHERE id = ?", (status, key))

    def connection(self, account: str, status: str) -> None:
        """Record heartbeat/connection state; error text must be a safe error category."""
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO connections(account, status, updated) VALUES (?, ?, ?)",
                (account, status[:80], time.time()),
            )

    def status(self) -> dict:
        """Return safe local operational counts without message text, tokens or user IDs."""
        with self.connect(write=False) as db:
            return {
                "tasks": dict(db.execute("SELECT status, COUNT(*) FROM messages GROUP BY status").fetchall()),
                "replies": dict(db.execute("SELECT status, COUNT(*) FROM outbox GROUP BY status").fetchall()),
                "connections": [dict(row) for row in db.execute("SELECT * FROM connections")],
                "undelivered": [
                    dict(row)
                    for row in db.execute(
                        "SELECT id, account, status, attempts FROM outbox WHERE status IN ('failed', 'unknown') ORDER BY created DESC LIMIT 20"
                    )
                ],
            }
