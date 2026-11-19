"""Transactional schedule/occurrence ledger; a claimed occurrence is never silently replayed."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

from minisweagent.channels.credentials import private_directory
from minisweagent.scheduler.config import DEFAULT_DIRECTORY, JobSpec, next_occurrence, parse_schedule, utc_text
from minisweagent.tools import ToolError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, spec TEXT NOT NULL, schedule TEXT NOT NULL,
 state TEXT NOT NULL, next_at REAL, fired INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS executions (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
 slot REAL NOT NULL, manual INTEGER NOT NULL, status TEXT NOT NULL,
 snapshot TEXT NOT NULL, created_at REAL NOT NULL, finished_at REAL,
 result TEXT NOT NULL DEFAULT '{}', cancel INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS occurrence_once ON executions(job_id,slot) WHERE manual=0;
CREATE INDEX IF NOT EXISTS active_runs ON executions(job_id,status);
"""


class JobStore:
    """Store host-owned definitions privately; public views omit runtime configuration.

    Every mutation uses BEGIN IMMEDIATE so CLI, desktop and the daemon cannot
    claim the same occurrence. History survives edits/removal. Read-only queries
    on an absent store create no files. `now` is optional for deterministic callers.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY):
        self.directory = directory.expanduser().resolve()
        self.database = self.directory / "jobs.sqlite3"

    @contextmanager
    def _db(self, write: bool = False):
        if write:
            private_directory(self.directory)
        if not write and not self.database.exists():
            yield None
            return
        try:
            with closing(sqlite3.connect(self.database, timeout=10)) as db, db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA foreign_keys=ON")
                if write:
                    db.executescript(_SCHEMA)
                    if os.name != "nt":
                        self.database.chmod(0o600)
                    db.execute("BEGIN IMMEDIATE")
                yield db
        except sqlite3.Error as error:
            raise ToolError(f"Scheduler database unavailable: {type(error).__name__}.") from None

    @staticmethod
    def _row(db, key: str):
        row = db.execute("SELECT * FROM jobs WHERE id=? AND state!='removed'", (key,)).fetchone() if db else None
        if row is None:
            raise ToolError(f"Unknown scheduled job: {key!r}.")
        return row

    @staticmethod
    def _public(row) -> dict:
        spec = json.loads(row["spec"])
        return {
            "id": row["id"],
            "state": row["state"],
            "revision": row["revision"],
            "name": spec["name"],
            "prompt": spec["prompt"],
            "schedule": spec["schedule"],
            "timezone": spec["timezone"],
            "workspace": spec["workspace"],
            "skills": spec["skills"],
            "repeat": spec["repeat"],
            "fired": row["fired"],
            "next_run_at": utc_text(row["next_at"]) if row["next_at"] is not None else None,
            "model": spec["config"].get("model", {}).get("model_name"),
            "sandbox_profile": spec["config"].get("sandbox_profile"),
        }

    def create(self, value: dict | JobSpec, *, now: float | None = None) -> dict:
        """Persist a validated job; no process, provider or sandbox is started."""
        now = time.time() if now is None else now
        spec = JobSpec.model_validate(value)
        if not spec.workspace.is_dir():
            raise ToolError("The job workspace must exist.")
        schedule = parse_schedule(spec.schedule, spec.timezone, now)
        key = uuid4().hex[:12]
        with self._db(True) as db:
            db.execute(
                "INSERT INTO jobs(id,spec,schedule,state,next_at,created_at) VALUES (?,?,?,'scheduled',?,?)",
                (key, spec.model_dump_json(), json.dumps(schedule), schedule["next"], now),
            )
        return self.get(key)

    def get(self, key: str) -> dict:
        """Return safe display fields, excluding provider secrets and arbitrary config."""
        with self._db() as db:
            return self._public(self._row(db, key))

    def definition(self, key: str) -> JobSpec:
        """Read a host-internal definition for editing; it may contain private provider configuration."""
        with self._db() as db:
            return JobSpec.model_validate_json(self._row(db, key)["spec"])

    def list(self) -> list[dict]:
        """List visible jobs; availability does not imply that a daemon is running."""
        with self._db() as db:
            return (
                [
                    self._public(row)
                    for row in db.execute("SELECT * FROM jobs WHERE state!='removed' ORDER BY created_at")
                ]
                if db
                else []
            )

    def update(self, key: str, value: dict | JobSpec, *, revision: int | None = None, now: float | None = None) -> dict:
        """Replace settings atomically; snapshots of queued/running executions remain unchanged."""
        now = time.time() if now is None else now
        spec = JobSpec.model_validate(value)
        if not spec.workspace.is_dir():
            raise ToolError("The job workspace must exist.")
        schedule = parse_schedule(spec.schedule, spec.timezone, now)
        with self._db(True) as db:
            current = self._row(db, key)
            if revision is not None and current["revision"] != revision:
                raise ToolError("Job settings changed; refresh before updating.")
            state = "paused" if current["state"] == "paused" else "scheduled"
            db.execute(
                "UPDATE jobs SET spec=?,schedule=?,state=?,next_at=?,fired=0,revision=revision+1 WHERE id=?",
                (spec.model_dump_json(), json.dumps(schedule), state, schedule["next"], key),
            )
        return self.get(key)

    def control(self, key: str, action: str, *, now: float | None = None) -> dict:
        """Pause future runs, resume, remove, or enqueue a manual run; ongoing calls need cancel()."""
        now = time.time() if now is None else now
        if action not in {"pause", "resume", "remove", "run"}:
            raise ToolError("Choose pause, resume, remove or run.")
        with self._db(True) as db:
            row = self._row(db, key)
            if action == "run":
                if db.execute(
                    "SELECT 1 FROM executions WHERE job_id=? AND status IN ('queued','running')", (key,)
                ).fetchone():
                    raise ToolError("This job already has an active occurrence.")
                execution = uuid4().hex
                db.execute(
                    "INSERT INTO executions(id,job_id,slot,manual,status,snapshot,created_at) VALUES (?,?,?,1,'queued',?,?)",
                    (execution, key, now, row["spec"], now),
                )
                return {"execution_id": execution, "status": "queued"}
            state = {"pause": "paused", "resume": "scheduled", "remove": "removed"}[action]
            next_at = row["next_at"]
            if action == "resume" and next_at is None:
                raise ToolError(
                    "Completed jobs must be edited or explicitly run; resume cannot recreate a consumed occurrence."
                )
            db.execute("UPDATE jobs SET state=?,revision=revision+1 WHERE id=?", (state, key))
            if action in {"pause", "remove"}:
                db.execute(
                    "UPDATE executions SET status='cancelled',finished_at=? WHERE job_id=? AND status='queued'",
                    (now, key),
                )
        return {"id": key, "state": state}

    def claim_due(self, capacity: int, *, now: float | None = None) -> list[str]:
        """Account for due slots and reserve bounded work without overlapping the same job.

        One-shots expire outside grace. Recurring backlog coalesces into one run
        when catch_up=True; otherwise a skipped-range receipt is kept. The next
        slot is advanced in the same transaction as its unique occurrence receipt.
        """
        now = time.time() if now is None else now
        if capacity <= 0:
            return []
        with self._db(True) as db:
            queued = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM executions WHERE status='queued' ORDER BY created_at LIMIT ?", (capacity,)
                )
            ]
            for row in db.execute(
                "SELECT * FROM jobs WHERE state='scheduled' AND next_at<=? ORDER BY next_at", (now,)
            ).fetchall():
                if len(queued) >= capacity:
                    break
                if db.execute(
                    "SELECT 1 FROM executions WHERE job_id=? AND status IN ('queued','running')", (row["id"],)
                ).fetchone():
                    continue
                spec = JobSpec.model_validate_json(row["spec"])
                schedule = json.loads(row["schedule"])
                slot = row["next_at"]
                late = now - slot > spec.grace_seconds
                skipped = late and (schedule["kind"] == "once" or not spec.catch_up)
                next_at = next_occurrence(schedule, spec.timezone, slot, now)
                count = row["fired"] + (not skipped)
                if spec.repeat is not None and count >= spec.repeat:
                    next_at = None
                key = uuid4().hex
                result = {"reason": "missed_grace", "missed_until": utc_text(now)} if skipped else {}
                db.execute(
                    "INSERT INTO executions(id,job_id,slot,manual,status,snapshot,created_at,finished_at,result) VALUES (?,?,?,0,?,?,?,?,?)",
                    (
                        key,
                        row["id"],
                        slot,
                        "skipped" if skipped else "queued",
                        row["spec"],
                        now,
                        now if skipped else None,
                        json.dumps(result),
                    ),
                )
                db.execute(
                    "UPDATE jobs SET next_at=?,fired=?,state=? WHERE id=?",
                    (next_at, count, "completed" if next_at is None else "scheduled", row["id"]),
                )
                if not skipped:
                    queued.append(key)
            return queued

    def execution(self, key: str) -> dict:
        """Internal immutable execution snapshot; callers must not expose it as a public response."""
        with self._db() as db:
            row = db.execute("SELECT * FROM executions WHERE id=?", (key,)).fetchone() if db else None
            if row is None:
                raise ToolError("Unknown scheduled execution.")
            return dict(row)

    def history(self, key: str | None = None, limit: int = 50) -> list[dict]:
        """Return execution summaries and trace IDs without runtime secrets."""
        with self._db() as db:
            if db is None:
                return []
            rows = db.execute(
                "SELECT * FROM executions WHERE (? IS NULL OR job_id=?) ORDER BY created_at DESC LIMIT ?",
                (key, key, min(max(limit, 1), 1000)),
            )
            return [
                {
                    "id": row["id"],
                    "job_id": row["job_id"],
                    "scheduled_at": utc_text(row["slot"]),
                    "status": row["status"],
                    "manual": bool(row["manual"]),
                    "cancel_requested": bool(row["cancel"]),
                    "result": json.loads(row["result"]),
                }
                for row in rows
            ]

    def start(self, key: str) -> bool:
        """Fence process startup; a cancelled queued occurrence cannot execute."""
        with self._db(True) as db:
            return bool(
                db.execute(
                    "UPDATE executions SET status='running' WHERE id=? AND status='queued' AND cancel=0", (key,)
                ).rowcount
            )

    def finish(self, key: str, status: str, result: dict) -> None:
        """Settle a running execution once; late/stale completion cannot overwrite a terminal result."""
        with self._db(True) as db:
            db.execute(
                "UPDATE executions SET status=?,result=?,finished_at=? WHERE id=? AND status='running'",
                (status, json.dumps(result), time.time(), key),
            )

    def cancel(self, key: str) -> None:
        """Cancel queued work or signal a running process tree through its private cancel file."""
        with self._db(True) as db:
            row = db.execute("SELECT status FROM executions WHERE id=?", (key,)).fetchone()
            if row is None:
                raise ToolError("Unknown scheduled execution.")
            if row["status"] not in {"queued", "running"}:
                return
            db.execute(
                "UPDATE executions SET cancel=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE id=?",
                (key,),
            )
            if row["status"] == "running":
                path = self.directory / "artifacts" / key / "cancel"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

    def active(self) -> list[dict]:
        """Internal recovery view of running occurrences."""
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM executions WHERE status='running'")] if db else []
