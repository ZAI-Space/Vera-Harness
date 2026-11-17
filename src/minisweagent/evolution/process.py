"""Supervise bounded subprocess trees and serialize external experiment control."""

import json
import os
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from minisweagent.evolution.config import EvolutionError


def write_json(path: Path, value: dict) -> None:
    """Atomically replace a manifest in its directory; readers never see partial JSON."""
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.pending")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _process_stamp(pid: int) -> str | None:
    """Identify process creation, so recovery cannot kill an unrelated reused PID."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(
                handle, *[ctypes.byref(value) for value in (created, exited, kernel_time, user_time)]
            ):
                raise EvolutionError(f"Cannot identify process {pid} for recovery.")
            return (
                None
                if exited.dwHighDateTime or exited.dwLowDateTime
                else f"{created.dwHighDateTime}:{created.dwLowDateTime}"
            )
        finally:
            kernel.CloseHandle(handle)
    path = Path(f"/proc/{pid}/stat")
    if not path.exists():
        return None
    try:
        fields = path.read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except FileNotFoundError:
        return None


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def recover_processes(root: Path) -> None:
    """Reap previously owned subprocesses after acquiring the abandoned OS lock.

    Unknown costs remain reserved. No optimizer or verifier invocation is replayed.
    Only a PID with the recorded creation stamp can be terminated.
    """
    artifacts = root / "artifacts"
    leases = [*artifacts.glob("*/*.process.json"), *artifacts.glob("*/*/verifier.process.json")]
    for path in leases:
        if path.parent.name == "worker":
            continue  # Untrusted worker output is never a controller process lease.
        if not path.resolve().is_relative_to(root / "artifacts"):
            raise EvolutionError("A process lease escaped the artifact directory.")
        lease = json.loads(path.read_text(encoding="utf-8"))
        if lease["status"] == "running":
            if lease["stamp"] and _process_stamp(lease["pid"]) == lease["stamp"]:
                _kill_tree(lease["pid"])
            lease["status"] = "interrupted"
            write_json(path, lease)


@contextmanager
def experiment_lock(root: Path) -> Iterator[None]:
    """Reject simultaneous mutation; OS locks release even after controller crashes."""
    with (root / "controller.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            if (root / "controller.lock").stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise EvolutionError("Another evolution controller owns this experiment.") from error
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise EvolutionError("Another evolution controller owns this experiment.") from error
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def run_process(command: list[str], *, cwd: Path, env: dict, log: Path, timeout: int, cancel: Path) -> dict:
    """Run argv without a shell and reap the process tree on timeout/cancellation.

    Output goes straight to disk, avoiding pipe deadlocks and unbounded RAM use.
    Caller must reserve costs before starting; a killed paid request remains charged
    at its reserved bound because its provider-side completion may be unknown.
    """
    started = time.monotonic()
    reason = "returned"
    with log.open("wb") as output:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        lease_path = log.with_suffix(".process.json")
        lease = {"pid": process.pid, "stamp": _process_stamp(process.pid), "status": "running"}
        write_json(lease_path, lease)
        try:
            while process.poll() is None:
                if cancel.exists() or time.monotonic() - started >= timeout:
                    reason = "cancelled" if cancel.exists() else "timeout"
                    break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                _kill_tree(process.pid)
                process.wait(timeout=15)
            lease["status"] = reason
            write_json(lease_path, lease)
    return {"returncode": process.returncode, "status": reason, "seconds": time.monotonic() - started}
