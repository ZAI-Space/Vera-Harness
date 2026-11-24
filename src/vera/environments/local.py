"""Execute bounded local commands with the configured Bash runtime and process cleanup."""

import os
import platform
import signal
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from vera.exceptions import Submitted
from vera.utils.serialize import recursive_merge
from vera.utils.windows_bash import find_git_bash


class LocalEnvironmentConfig(BaseModel):
    cwd: str = ""
    env: dict[str, str] = {}
    timeout: int = 30
    bash_path: str = ""
    """Git Bash executable on Windows; defaults to VERA_BASH_PATH or automatic discovery."""
    shell_command: list[str] = []
    """Validated Bash executable/prefix; supports an explicitly selected WSL distribution."""


class LocalEnvironment:
    def __init__(self, *, config_class: type = LocalEnvironmentConfig, **kwargs):
        """This class executes bash commands directly on the local machine."""
        self.config = config_class(**kwargs)
        self.bash_path = (
            (find_git_bash(self.config.bash_path) if os.name == "nt" else self.config.bash_path)
            if not self.config.shell_command
            else ""
        )
        if os.name == "nt" and not (self.bash_path or self.config.shell_command):
            raise FileNotFoundError("Git Bash not found. Run start.cmd to set it up, or set VERA_BASH_PATH.")

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute a command in the local environment and return the result as a dict."""
        command = action.get("command", "")
        cwd = cwd or self.config.cwd or os.getcwd()
        try:
            result = _run(
                command,
                cwd,
                os.environ | self.config.env,
                timeout or self.config.timeout,
                self.bash_path,
                self.config.shell_command,
                self.config.env,
            )
            output = {"output": result.stdout, "returncode": result.returncode, "exception_info": ""}
        except Exception as e:
            raw_output = getattr(e, "output", None)
            raw_output = (
                raw_output.decode("utf-8", errors="replace") if isinstance(raw_output, bytes) else (raw_output or "")
            )
            output = {
                "output": raw_output,
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }
        self._check_finished(output)
        return output

    def _check_finished(self, output: dict):
        """Raises Submitted if the output indicates task completion."""
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {"exit_status": "Submitted", "submission": submission},
                }
            )

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), platform.uname()._asdict(), os.environ, kwargs)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }


def _run(
    command: str,
    cwd: str,
    env: dict[str, str],
    timeout: int,
    bash_path: str = "",
    shell_command: list[str] | None = None,
    configured_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a command with process-tree termination and bounded output draining on timeout."""
    if os.name == "nt":
        env = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"} | env
    prefix = list(shell_command or ([bash_path] if bash_path else []))
    if prefix and Path(prefix[0]).name.lower() in {"wsl", "wsl.exe"}:
        prefix[1:1] = ["--cd", str(Path(cwd).resolve())]
        # WSL imports only listed variables. Forward explicit overrides, preserving
        # existing user-selected path/direction flags and the distro's default PATH.
        shared = env.get("WSLENV", "").split(":")
        names = {item.partition("/")[0] for item in shared}
        configured_names = set(configured_env or {}) - {"WSLENV"}
        if os.name == "nt":
            configured_names.update({"PYTHONIOENCODING", "PYTHONUTF8"})
        shared.extend(sorted(configured_names - names))
        env = env | {"WSLENV": ":".join(item for item in shared if item)}
    process = subprocess.Popen(
        [*prefix, "--noprofile", "--norc", "-c", command] if prefix else command,
        shell=not bool(prefix),
        text=True,
        cwd=cwd,
        env=env,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            try:
                subprocess.run(
                    [
                        str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass  # Still bound pipe draining if taskkill is unavailable or unresponsive.
            finally:
                if process.poll() is None:
                    process.kill()
        try:
            stdout, _ = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            stdout = error.output or b""
        raise subprocess.TimeoutExpired(command, timeout, output=stdout)
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout)
