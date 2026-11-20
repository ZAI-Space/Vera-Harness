"""Run real backend commands from GUI Python and report console allocation.

Invoked by test_background_process, not a replacement process implementation.
The child uses Win32 console APIs so even a transient hidden console is detected.
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
from pathlib import Path


def console_state() -> dict:
    """Report the current process console handle and its visible-window state."""
    from ctypes import wintypes

    kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
    kernel.GetConsoleWindow.restype = wintypes.HWND
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    handle = kernel.GetConsoleWindow()
    return {"allocated": bool(handle), "visible": bool(handle and user.IsWindowVisible(handle))}


def main() -> None:
    """Exercise probes, supervision and actual Git handlers without a parent console."""
    if sys.argv[1] == "child":
        print(json.dumps(console_state()), flush=True)
        raise SystemExit(int(sys.argv[2]) if len(sys.argv) > 2 else 0)

    from vera.desktop.service import DesktopService
    from vera.environments.sandbox import _probe
    from vera.evolution.process import _process_stamp, run_process
    from vera.evolution.repository import git
    from vera.plugins.source import _git
    from vera.terminal.files import ProjectFiles
    from vera.utils.process import BACKGROUND_CREATION_FLAGS

    root = Path(sys.argv[1])
    console_python = os.environ["VERA_TEST_CONSOLE_PYTHON"]
    command = [console_python, str(Path(__file__).resolve()), "child"]
    results = {"parent": console_state()}
    for index in range(3):
        results[f"probe{index}"] = json.loads(_probe(command))
    outcome = run_process(
        command, cwd=root, env=os.environ.copy(), log=root / "job.log", timeout=10, cancel=root / "cancel"
    )
    results["job"] = {"status": outcome["status"], **json.loads((root / "job.log").read_text())}
    failed = run_process(
        [*command, "7"], cwd=root, env=os.environ.copy(), log=root / "failed.log", timeout=10, cancel=root / "cancel"
    )
    results["failed"] = {"status": failed["status"], "returncode": failed["returncode"]}
    assert _probe([*command, "7"]) is None

    for name, duration in (("timeout", 0.8), ("cancelled", 10)):
        script = "import os,time;from pathlib import Path;Path('child.pid').write_text(str(os.getpid()));time.sleep(30)"
        marker = root / f"{name}.stop"
        timer = threading.Timer(1, marker.touch) if name == "cancelled" else None
        if timer:
            timer.start()
        try:
            result = run_process(
                [console_python, "-c", script],
                cwd=root,
                env=os.environ.copy(),
                log=root / f"{name}.log",
                timeout=duration,
                cancel=marker,
            )
            child_pid = int((root / "child.pid").read_text())
            results[name] = {"status": result["status"], "childReaped": _process_stamp(child_pid) is None}
        finally:
            if timer:
                timer.join()

    subprocess.run(
        ["git", "init", "--initial-branch=console-test", str(root)],
        check=True,
        capture_output=True,
        creationflags=BACKGROUND_CREATION_FLAGS,
    )
    (root / "example.py").write_text("print('console-test')\n", encoding="utf-8")
    results["git"] = git(root, "branch", "--show-current").strip()
    results["pluginGit"] = _git(root, "branch", "--show-current")
    results["files"] = ProjectFiles(root).list("example.py")
    service = DesktopService(root / "desktop")
    try:
        results["branch"] = service.invoke("getGitBranch", {"cwd": str(root)})
        results["branches"] = service.invoke("listGitBranches", {"cwd": str(root)})
    finally:
        service.close()
    (root / "results.json").write_text(json.dumps(results), encoding="utf-8")


if __name__ == "__main__":
    main()
