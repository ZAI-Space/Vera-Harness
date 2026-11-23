"""Supervise bounded subprocess trees and serialize external experiment control."""

import errno
import json
import os
import signal
import stat
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from vera.evolution.config import EvolutionError


def read_optimizer_result(path: Path) -> dict:
    """Read at most 1 MiB from a single regular optimizer result, without following links.

    Results cross from the optimizer into the trusted controller. Missing files
    still raise FileNotFoundError; links, special files and oversized data fail
    before an untrusted file can block or exhaust controller memory.
    """
    maximum = 1024 * 1024
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
        raise EvolutionError("Optimizer results must be single regular files, not symbolic links or special files.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (initial.st_dev, initial.st_ino) != (opened.st_dev, opened.st_ino)
            or opened.st_size > maximum
        ):
            raise EvolutionError("Optimizer result changed identity, is not regular, or exceeds 1 MiB.")
        payload = stream.read(maximum + 1)
        final = os.fstat(stream.fileno())
        if len(payload) > maximum or (opened.st_size, opened.st_mtime_ns) != (final.st_size, final.st_mtime_ns):
            raise EvolutionError("Optimizer result changed during reading or exceeds 1 MiB.")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise EvolutionError("Optimizer result must be a JSON object.")
    return value


def read_json(path: Path) -> dict:
    """Read a complete manifest, briefly retrying Windows sharing/access errors.

    Persistent permission failures, missing files and invalid JSON still raise.
    This is safe alongside atomic replacement; it never accepts partial state.
    """
    for _ in range(19):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError as error:
            if os.name != "nt":
                raise
            # Python's CRT-backed open can expose EACCES without a Win32 code.
            is_access_error = error.winerror in {5, 32, 33} or (error.winerror is None and error.errno == errno.EACCES)
            if not is_access_error:
                raise
            time.sleep(0.01)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    """Atomically replace a manifest in its directory; readers never see partial JSON."""
    # Keep the temporary basename short for valid destinations near Windows MAX_PATH.
    temporary = path.with_name(f".{uuid4().hex}.pending")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    # Windows readers briefly prevent replacement; retain atomic publication and
    # retry only transient access/sharing errors, never write partial JSON in place.
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            if os.name != "nt" or error.winerror not in {5, 32, 33} or attempt == 19:
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(0.01)


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
        # Bash/MCP commands may create their own sessions. Capture descendants
        # before killing the owner, while /proc still preserves their ancestry.
        processes = {}
        for path in Path("/proc").glob("[0-9]*/stat"):
            try:
                fields = path.read_text().rsplit(")", 1)[1].split()
                processes[int(path.parent.name)] = (int(fields[1]), fields[19])
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        descendants = []
        parents = {pid}
        while parents:
            children = {child for child, (parent, _) in processes.items() if parent in parents and child not in parents}
            descendants.extend((child, processes[child][1]) for child in children)
            parents = children
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for child, stamp in reversed(descendants):
            try:
                if _process_stamp(child) == stamp:
                    os.kill(child, signal.SIGKILL)
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
                # Sending SIGKILL is asynchronous. Confirm the old owner has
                # exited before publishing recovery or dispatching new work.
                deadline = time.monotonic() + 5
                while _process_stamp(lease["pid"]) == lease["stamp"]:
                    if time.monotonic() >= deadline:
                        raise EvolutionError(f"Process {lease['pid']} did not exit during recovery.")
                    time.sleep(0.01)
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
            # Windows may signal process exit before its file locks are released.
            # Bound the grace period; a live controller still retains ownership.
            for attempt in range(20):
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except PermissionError as error:
                    if attempt == 19:
                        raise EvolutionError("Another evolution controller owns this experiment.") from error
                    time.sleep(0.01)
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


def run_process(command: list[str], *, cwd: Path, env: dict, log: Path, timeout: int | None, cancel: Path) -> dict:
    """Run argv without a shell and reap on failure, timeout or cancellation.

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
        try:
            lease = {"pid": process.pid, "stamp": _process_stamp(process.pid), "status": "running"}
            write_json(lease_path, lease)
            while process.poll() is None:
                if cancel.exists() or (timeout is not None and time.monotonic() - started >= timeout):
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
