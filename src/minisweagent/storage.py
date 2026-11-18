"""Persist run receipts and conversation checkpoints for inspection, cancellation and recovery."""

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from minisweagent import global_config_dir
from minisweagent.exceptions import InterruptAgentFlow, Submitted
from minisweagent.memory.context import ContextModel

if TYPE_CHECKING:
    from minisweagent.agents.default import DefaultAgent

DEFAULT_STORAGE_PATH = global_config_dir / "runs.sqlite3"

_SCHEMA = (
    """CREATE TABLE runs (
        id TEXT PRIMARY KEY,
        parent_id TEXT REFERENCES runs(id),
        role TEXT,
        status TEXT NOT NULL,
        exit_reason TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        model_calls INTEGER NOT NULL DEFAULT 0,
        cost REAL NOT NULL DEFAULT 0,
        trajectory_path TEXT
    )""",
    "CREATE INDEX runs_parent ON runs(parent_id)",
    """CREATE TABLE tool_calls (
        id INTEGER PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id),
        provider_call_id TEXT,
        tool TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        status TEXT NOT NULL,
        returncode INTEGER
    )""",
    "CREATE INDEX tool_calls_run ON tool_calls(run_id)",
)


class StorageConfig(BaseModel):
    """Enable local storage by adding a storage section or selecting a database path."""

    model_config = ConfigDict(extra="forbid")
    path: Path = DEFAULT_STORAGE_PATH


class StorageError(RuntimeError):
    """The runtime could not read or persist the run journal."""


@contextmanager
def _run_lock(database: Path, run_id: str) -> Iterator[None]:
    """Hold a process-owned lock. The OS releases it when the process exits."""
    directory = database.with_name(f"{database.name}.locks")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle = (directory / run_id).open("a+b")
    except OSError as error:
        raise StorageError(f"Could not open run lock: {error}") from error
    with handle:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise StorageError(
                f"Cannot acquire the lock for run {run_id!r}. Check whether it is still active."
            ) from None
        yield


_RECOVERY_SCHEMA = (
    "ALTER TABLE runs ADD COLUMN cancel_requested_at TEXT",
    "ALTER TABLE runs ADD COLUMN resumed_from TEXT REFERENCES runs(id)",
    "ALTER TABLE runs ADD COLUMN workspace TEXT",
    "ALTER TABLE tool_calls ADD COLUMN action TEXT",
    "CREATE UNIQUE INDEX runs_resume ON runs(resumed_from)",
    """CREATE TABLE checkpoints (
        run_id TEXT PRIMARY KEY REFERENCES runs(id),
        task TEXT NOT NULL,
        adapter TEXT NOT NULL,
        runtime TEXT NOT NULL,
        messages TEXT NOT NULL,
        last_receipt INTEGER NOT NULL
    )""",
)


@dataclass(frozen=True)
class ResumeCheckpoint:
    """Conversation and task from the last finished step."""

    task: str
    messages: list[dict]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _adapter_name(agent: "DefaultAgent") -> str:
    model = agent.model
    while isinstance(model, ContextModel):
        model = model._model
    model_type = type(model)
    return f"{model_type.__module__}.{model_type.__qualname__}"


def _runtime_name(agent: "DefaultAgent", policy: str) -> str:
    runtime_type = type(agent.env)
    config = getattr(agent.env, "config", None)
    payload = config.model_dump_json() if isinstance(config, BaseModel) else ""
    digest = hashlib.sha256(json.dumps([payload, policy]).encode()).hexdigest()
    return f"{runtime_type.__module__}.{runtime_type.__qualname__}:{digest}"


class RunStore:
    """Store runs in SQLite using a short transaction per durable update."""

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()

    @contextmanager
    def _connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        mode = "rwc" if write else "ro"
        try:
            if write:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(f"{self.path.as_uri()}?mode={mode}", uri=True, timeout=5)) as db, db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys = ON")
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0 and write:
                    for statement in _SCHEMA:
                        db.execute(statement)
                    version = 1
                if version == 1 and write:
                    for statement in _RECOVERY_SCHEMA:
                        db.execute(statement)
                    db.execute("PRAGMA user_version = 2")
                elif version not in (1, 2):
                    raise StorageError(f"Unsupported run database schema version {version}.")
                yield db
        except (OSError, sqlite3.Error) as error:
            raise StorageError(f"Run database {self.path}: {error}") from error

    @contextmanager
    def track(
        self,
        agent: "DefaultAgent",
        *,
        run_id: str | None = None,
        parent_id: str | None = None,
        role: str | None = None,
        resume_from: str | None = None,
        reconciliation: str | None = None,
        workspace: Path | None = None,
        runtime_policy: str = "",
    ) -> Iterator["RunRecord"]:
        """Record one agent run and restore its prior binding when the run exits."""
        if agent.run_record is not None:
            raise StorageError("An agent already has an active run record.")
        run_id = run_id or uuid4().hex
        if len(run_id) != 32 or any(character not in "0123456789abcdef" for character in run_id):
            raise StorageError("Run IDs must be 32 lowercase hexadecimal characters.")
        workspace = (workspace or Path.cwd()).resolve()
        runtime = _runtime_name(agent, runtime_policy)
        trajectory = agent.config.output_path
        trajectory_path = trajectory.resolve() if trajectory else None
        if trajectory_path == self.path:
            raise StorageError("The trajectory and run database need separate paths.")
        with _run_lock(self.path, run_id):
            with self._connect(write=True) as db:
                checkpoint = (
                    self._claim_resume(db, resume_from, agent, workspace, runtime, trajectory_path, reconciliation)
                    if resume_from
                    else None
                )
                db.execute(
                    """INSERT INTO runs(id, parent_id, role, status, started_at, trajectory_path, resumed_from, workspace)
                       VALUES (?, ?, ?, 'running', ?, ?, ?, ?)""",
                    (
                        run_id,
                        parent_id,
                        role,
                        _utc_now(),
                        str(trajectory_path) if trajectory_path else None,
                        resume_from,
                        str(workspace),
                    ),
                )
                if checkpoint is not None:
                    db.execute(
                        """INSERT INTO checkpoints(run_id, task, adapter, runtime, messages, last_receipt)
                           VALUES (?, ?, ?, ?, ?, 0)""",
                        (
                            run_id,
                            checkpoint.task,
                            _adapter_name(agent),
                            runtime,
                            json.dumps(checkpoint.messages),
                        ),
                    )
            record = RunRecord(self, run_id, agent, runtime, parent_id, checkpoint)
            with self._observe(agent, record):
                yield record

    @contextmanager
    def _observe(self, agent: "DefaultAgent", record: "RunRecord") -> Iterator[None]:
        agent.run_record = record
        try:
            yield
        except BaseException as error:
            record.finish("cancelled" if isinstance(error, KeyboardInterrupt) else "failed", type(error).__name__)
            raise
        else:
            extra = agent.messages[-1].get("extra", {}) if agent.messages else {}
            exit_reason = extra.get("exit_status")
            status = {
                "Submitted": "completed",
                "Cancelled": "cancelled",
                "TimeExceeded": "stopped",
                "LimitsExceeded": "stopped",
            }.get(exit_reason, "failed")
            record.finish(status, exit_reason)
        finally:
            agent.run_record = None

    def _claim_resume(self, db, run_id, agent, workspace, runtime, trajectory_path, reconciliation) -> ResumeCheckpoint:
        source = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if source is None:
            raise StorageError(f"No run with ID {run_id!r}.")
        if source["parent_id"] is not None or source["status"] == "completed":
            raise StorageError("Resume a failed, stopped, cancelled or interrupted top-level run.")
        if db.execute("SELECT 1 FROM runs WHERE resumed_from = ?", (run_id,)).fetchone():
            raise StorageError("This run already has a continuation. Use its run ID.")
        checkpoint = db.execute("SELECT * FROM checkpoints WHERE run_id = ?", (run_id,)).fetchone()
        if checkpoint is None:
            raise StorageError("This run has no saved checkpoint.")
        if (
            source["workspace"] != str(workspace)
            or checkpoint["adapter"] != _adapter_name(agent)
            or checkpoint["runtime"] != runtime
        ):
            raise StorageError("Resume with the original workspace, execution configuration and model adapter.")
        if trajectory_path and str(trajectory_path) == source["trajectory_path"]:
            raise StorageError("Choose a new trajectory output path for the continuation.")
        unresolved = db.execute(
            """SELECT 1 FROM tool_calls AS tool JOIN runs AS run ON run.id = tool.run_id
               WHERE (tool.run_id = ? AND (tool.id > ? OR tool.status = 'unknown'))
                  OR (run.parent_id = ? AND tool.status = 'unknown') LIMIT 1""",
            (run_id, checkpoint["last_receipt"], run_id),
        ).fetchone()
        if unresolved and not reconciliation:
            raise StorageError(
                "Review the tool receipts and workspace, then pass --reconcile with the verified outcome."
            )
        if source["status"] == "running":
            with _run_lock(self.path, run_id):
                db.execute(
                    """UPDATE runs SET status = 'interrupted', exit_reason = 'ProcessExited', ended_at = ?
                       WHERE status = 'running' AND (id = ? OR parent_id = ?)""",
                    (_utc_now(), run_id, run_id),
                )
        messages = json.loads(checkpoint["messages"])
        if reconciliation:
            messages.append(
                agent.model.format_message(
                    role="user",
                    content=f"Verified outcome since the last checkpoint. Avoid repeating completed work.\n\n{reconciliation}",
                )
            )
        return ResumeCheckpoint(checkpoint["task"], messages)

    def request_cancel(self, run_id: str) -> None:
        """Request cooperative cancellation of an active run."""
        if not self.path.is_file():
            raise StorageError(f"No run database at {self.path}.")
        with self._connect(write=True) as db:
            result = db.execute(
                "UPDATE runs SET cancel_requested_at = COALESCE(cancel_requested_at, ?) WHERE id = ? AND status = 'running'",
                (_utc_now(), run_id),
            )
            if not result.rowcount:
                raise StorageError(f"No open run with ID {run_id!r}.")

    def list_runs(self, limit: int = 20) -> list[dict]:
        """Return recent runs, including still-open records from a previous process."""
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT ?", (limit,))]

    def get_run(self, run_id: str) -> dict | None:
        """Return a run, its direct children, and ordered tool receipts in one read transaction."""
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            children = db.execute("SELECT * FROM runs WHERE parent_id = ? ORDER BY rowid", (run_id,))
            calls = []
            for call in db.execute("SELECT * FROM tool_calls WHERE run_id = ? ORDER BY id", (run_id,)):
                receipt = dict(call)
                if receipt.get("action") is not None:
                    receipt["action"] = json.loads(receipt["action"])
                calls.append(receipt)
            return dict(row) | {
                "children": [dict(child) for child in children],
                "tool_calls": calls,
            }


@dataclass(frozen=True)
class RunRecord:
    """Record actual dispatches for a single active run."""

    store: RunStore
    id: str
    agent: "DefaultAgent"
    runtime: str
    parent_id: str | None = None
    resume: ResumeCheckpoint | None = None

    def checkpoint(self, task: str) -> None:
        """Persist a conversation only at a completed step boundary."""
        with self.store._connect(write=True) as db:
            db.execute(
                """INSERT OR REPLACE INTO checkpoints(run_id, task, adapter, runtime, messages, last_receipt)
                   VALUES (?, ?, ?, ?, ?, (SELECT COALESCE(MAX(id), 0) FROM tool_calls WHERE run_id = ?))""",
                (
                    self.id,
                    task,
                    _adapter_name(self.agent),
                    self.runtime,
                    json.dumps(self.agent.messages),
                    self.id,
                ),
            )
            db.execute(
                "UPDATE runs SET model_calls = ?, cost = ? WHERE id = ?",
                (self.agent.n_calls, self.agent.cost, self.id),
            )

    def check_cancelled(self) -> None:
        """Stop before the next step or dispatch if this run or its parent was cancelled."""
        with self.store._connect() as db:
            self._check_cancelled(db)

    def _check_cancelled(self, db: sqlite3.Connection) -> None:
        if db.execute(
            "SELECT 1 FROM runs WHERE id IN (?, ?) AND cancel_requested_at IS NOT NULL",
            (self.id, self.parent_id),
        ).fetchone():
            raise InterruptAgentFlow(
                {"role": "exit", "content": "Run cancelled.", "extra": {"exit_status": "Cancelled", "submission": ""}}
            )

    def execute(self, action: dict, dispatch: Callable[[dict], dict]) -> dict:
        """Commit intent before dispatch and persist the resulting receipt when available."""
        with self.store._connect(write=True) as db:
            self._check_cancelled(db)
            db.execute(
                "UPDATE runs SET model_calls = ?, cost = ? WHERE id = ?",
                (self.agent.n_calls, self.agent.cost, self.id),
            )
            receipt = db.execute(
                """INSERT INTO tool_calls(run_id, provider_call_id, tool, started_at, status, action)
                   VALUES (?, ?, ?, ?, 'unknown', ?)""",
                (self.id, action.get("tool_call_id"), action.get("tool", "bash"), _utc_now(), json.dumps(action)),
            ).lastrowid
        try:
            output = dispatch(action)
        except Submitted:
            self._settle(receipt, "returned", 0)
            raise
        except BaseException:
            self._settle(receipt, "unknown", None)
            raise
        else:
            returncode = output.get("returncode")
            is_unknown = returncode is None or returncode < 0 or output.get("extra", {}).get("result_unknown", False)
            status = "unknown" if is_unknown else "returned"
            self._settle(receipt, status, returncode)
            return output

    def _settle(self, receipt: int | None, status: str, returncode: int | None) -> None:
        with self.store._connect(write=True) as db:
            db.execute(
                "UPDATE tool_calls SET status = ?, ended_at = ?, returncode = ? WHERE id = ?",
                (status, _utc_now(), returncode, receipt),
            )
            db.execute(
                "UPDATE runs SET model_calls = ?, cost = ? WHERE id = ?",
                (self.agent.n_calls, self.agent.cost, self.id),
            )

    def finish(self, status: str, exit_reason: str | None) -> None:
        """Store the terminal status and final model usage."""
        with self.store._connect(write=True) as db:
            db.execute(
                "UPDATE runs SET status = ?, exit_reason = ?, ended_at = ?, model_calls = ?, cost = ? WHERE id = ?",
                (status, exit_reason, _utc_now(), self.agent.n_calls, self.agent.cost, self.id),
            )
