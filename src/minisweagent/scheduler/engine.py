"""An independent scheduler service with OS ownership, bounded workers and crash recovery."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event

from minisweagent.channels.credentials import private_directory
from minisweagent.evolution.config import EvolutionError
from minisweagent.evolution.process import (
    _process_stamp,
    experiment_lock,
    read_json,
    recover_processes,
    run_process,
    write_json,
)
from minisweagent.scheduler.config import DEFAULT_DIRECTORY, JobSpec
from minisweagent.scheduler.store import JobStore
from minisweagent.tools import ToolError


def service_status(directory: Path = DEFAULT_DIRECTORY) -> dict:
    """Return live ownership, not just the presence of a stale PID file."""
    path = directory.expanduser().resolve() / "service.json"
    if not path.exists():
        return {"running": False}
    try:
        lease = read_json(path)
        live = bool(lease.get("stamp")) and _process_stamp(lease["pid"]) == lease["stamp"]
        return {"running": live, "pid": lease["pid"] if live else None}
    except (OSError, ValueError, KeyError):
        return {"running": False}


class Scheduler:
    """One service owns a store; each tick dispatches at most the available worker slots.

    Use `with Scheduler(...).owned(): tick(); wait()` for one-shot dispatch, or
    `serve()` for a daemon. Recovered unknown executions are never replayed. A
    job that ran to completion before the controller died is settled from its
    atomic result file. Side effects cannot be guaranteed exactly once across crashes.
    """

    def __init__(self, directory: Path = DEFAULT_DIRECTORY, *, workers: int = 2):
        if not 1 <= workers <= 16:
            raise ToolError("Choose 1-16 scheduler workers.")
        self.store = JobStore(directory)
        self.directory = self.store.directory
        self.workers = workers
        self.pool = None
        self.pending = {}

    @contextmanager
    def owned(self):
        """Acquire cross-process ownership, reconcile old children, then release after shutdown."""
        private_directory(self.directory)
        try:
            lock = experiment_lock(self.directory)
            lock.__enter__()
        except EvolutionError:
            raise ToolError("Another scheduler owns this state directory.") from None
        try:
            recover_processes(self.directory)
            for row in self.store.active():
                result = self._result(row["id"], {"status": "interrupted", "reason": "controller_exited; not replayed"})
                self.store.finish(row["id"], result["status"], result)
            self.pool = ThreadPoolExecutor(max_workers=self.workers)
            yield self
        finally:
            if self.pool:
                for key in self.pending:
                    self.store.cancel(key)
                self.pool.shutdown(wait=True)
                self.pool = None
            lock.__exit__(None, None, None)

    def _result(self, key: str, fallback: dict) -> dict:
        path = self.directory / "artifacts" / key / "result.json"
        try:
            result = read_json(path)
        except (OSError, ValueError):
            return fallback
        return (
            result
            if isinstance(result, dict)
            and result.get("status") in {"completed", "failed", "cancelled", "timeout", "interrupted"}
            else fallback
        )

    def _execute(self, key: str) -> None:
        if not self.store.start(key):
            return
        row = self.store.execution(key)
        output = private_directory(self.directory / "artifacts" / key)
        try:
            spec = JobSpec.model_validate_json(row["snapshot"])
            environment = os.environ | {
                "MSWEA_SILENT_STARTUP": "1",
                "MSWEA_CONFIGURED": "true",
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": os.pathsep.join(
                    filter(
                        None,
                        [
                            str(Path(__file__).resolve().parents[2]),
                            str(Path(__file__).resolve().parents[3]),
                            os.environ.get("PYTHONPATH", ""),
                        ],
                    )
                ),
            }
            outcome = run_process(
                [sys.executable, "-m", "minisweagent.scheduler.worker", str(self.directory), key],
                cwd=spec.workspace,
                env=environment,
                log=output / "process.log",
                timeout=spec.timeout + 5,
                cancel=output / "cancel",
            )
            fallback = {"status": "failed", "reason": "worker_exited", "returncode": outcome["returncode"]}
            if outcome["status"] in {"cancelled", "timeout"}:
                result = {"status": outcome["status"], "reason": outcome["status"], "run_id": key}
            else:
                result = self._result(key, fallback)
            self.store.finish(key, result["status"], result)
        except Exception as error:
            self.store.finish(key, "failed", {"error_type": type(error).__name__, "run_id": key})

    def tick(self, *, now: float | None = None) -> list[str]:
        """Reap finished work and enqueue due slots; requires owned(), returns dispatched IDs."""
        if self.pool is None:
            raise ToolError("Acquire scheduler ownership before ticking.")
        for key, future in list(self.pending.items()):
            if future.done():
                future.result()
                del self.pending[key]
        keys = self.store.claim_due(self.workers - len(self.pending), now=now)
        for key in keys:
            self.pending[key] = self.pool.submit(self._execute, key)
        return keys

    def wait(self) -> None:
        """Wait for this batch only; no additional due work is created."""
        for future in self.pending.values():
            future.result()
        self.pending.clear()

    def serve(self, *, interval: float = 1, stop: Event | None = None) -> None:
        """Run until requested to stop; active child trees are cancelled before returning."""
        if not 0.05 <= interval <= 60:
            raise ToolError("Choose a polling interval between 0.05 and 60 seconds.")
        stop = stop or Event()
        with self.owned():
            stop_path = self.directory / "service.stop"
            stop_path.unlink(missing_ok=True)
            write_json(self.directory / "service.json", {"pid": os.getpid(), "stamp": _process_stamp(os.getpid())})
            try:
                while not stop.is_set() and not stop_path.exists():
                    self.tick()
                    stop.wait(interval)
            finally:
                (self.directory / "service.json").unlink(missing_ok=True)


def start_service(directory: Path = DEFAULT_DIRECTORY, *, workers: int = 2) -> dict:
    """Launch a detached scheduler, preserving environment credentials; never install an OS service."""
    directory = directory.expanduser().resolve()
    if service_status(directory)["running"]:
        return service_status(directory)
    private_directory(directory)
    command = [
        sys.executable,
        "-m",
        "minisweagent.run.utilities.cron",
        "--state",
        str(directory),
        "serve",
        "--workers",
        str(workers),
    ]
    with (directory / "service.log").open("ab") as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=os.name != "nt",
            creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
        )
    for _ in range(100):
        status = service_status(directory)
        if status["running"]:
            return status
        if process.poll() is not None:
            raise ToolError("Scheduler could not start; inspect its private service.log.")
        time.sleep(0.1)
    raise ToolError("Scheduler startup timed out; inspect service status before retrying.")


def stop_service(directory: Path = DEFAULT_DIRECTORY) -> dict:
    """Request orderly shutdown without killing unrelated processes."""
    directory = directory.expanduser().resolve()
    status = service_status(directory)
    if status["running"]:
        (directory / "service.stop").touch()
    return {"stop_requested": status["running"]}
