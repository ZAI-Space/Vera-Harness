"""Discover installed Bash runtimes and resolve explicit desktop selections."""

import os
import shutil
import subprocess
import time
from pathlib import Path

from vera.utils.windows_bash import find_git_bash

_cached = (0.0, [])


def command_shells(*, refresh: bool = False) -> list[dict]:
    """Probe installed Bash executables/WSL distributions; never download or install a shell."""
    global _cached
    if not refresh and time.monotonic() - _cached[0] < 30:
        return _cached[1]
    rows = [{"id": "system", "label": "系统默认（自动选择 Bash）", "command": []}]
    if os.name == "nt":
        if executable := find_git_bash():
            rows.append({"id": "git-bash", "label": "Git Bash", "command": [executable]})
        if wsl := shutil.which("wsl"):
            result = subprocess.run(
                [wsl, "--list", "--quiet"], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
            )
            for name in result.stdout.decode("utf-16-le", errors="replace").replace("\0", "").splitlines():
                name = name.strip()
                if not name or name.startswith("docker-desktop"):
                    continue
                prefix = [wsl, "--distribution", name, "--exec", "bash"]
                try:
                    probe = subprocess.run(
                        [*prefix, "--noprofile", "--norc", "-c", "printf VERA_BASH_READY"],
                        capture_output=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                except subprocess.TimeoutExpired:
                    continue
                if probe.returncode == 0 and probe.stdout == b"VERA_BASH_READY":
                    rows.append({"id": "wsl:" + name, "label": f"WSL · {name} · Bash", "command": prefix})
    if executable := shutil.which("bash"):
        path = Path(executable).resolve()
        if "system32" not in str(path).lower() and not any(row["command"] == [str(path)] for row in rows):
            rows.append({"id": "bash", "label": f"Bash · {path}", "command": [str(path)]})
    _cached = (time.monotonic(), rows)
    return rows


def shell_command(selection: str) -> list[str]:
    """Reject a removed runtime rather than silently executing commands in another shell."""
    if selection == "system":
        return []
    if selection == "git-bash" and os.name == "nt":
        if executable := find_git_bash():
            return [executable]
    row = next((item for item in command_shells() if item["id"] == selection), None)
    if row is None:
        raise ValueError("所选 Bash 环境不可用，请重新检测命令 Shell 并选择可用环境。")
    return row["command"]
