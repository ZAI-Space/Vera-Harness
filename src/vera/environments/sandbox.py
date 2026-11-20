"""Select and supervise optional workspace isolation for the interactive runtime."""

import csv
import io
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vera import Environment
from vera.environments import get_environment
from vera.environments.docker import DockerEnvironment
from vera.environments.extra.bubblewrap import BubblewrapEnvironment
from vera.tools import ToolError
from vera.utils.process import BACKGROUND_CREATION_FLAGS

_WORKDIR = "/workspace"


class SandboxMode(str, Enum):
    """Execution modes exposed to the user."""

    AUTO = "auto"
    DOCKER = "docker"
    BUBBLEWRAP = "bubblewrap"
    LOCAL = "local"


class SandboxConfig(BaseModel):
    """Workspace boundary and explicit exceptions for tools running outside it."""

    model_config = ConfigDict(extra="forbid")
    mode: SandboxMode = SandboxMode.AUTO
    workspace: Path = Path(".")
    workspace_access: Literal["read-write", "read-only"] = "read-write"
    timeout: int = Field(default=30, ge=1, le=3600)
    docker_image: str = "python:3.12-slim"
    host_mcp_servers: list[str] = Field(default_factory=list)
    remote_mcp_servers: list[str] = Field(default_factory=list)
    allow_web_tools: bool = False

    def check_external_tools(self, *, web_enabled: bool, stdio: set[str], http: set[str]) -> None:
        """Require configured permissions before starting host MCP or enabling network tools."""
        if self.mode == SandboxMode.LOCAL:
            return
        denied = []
        if missing := stdio.difference(self.host_mcp_servers):
            denied.append(f"set sandbox.host_mcp_servers for host stdio MCP: {', '.join(sorted(missing))}")
        if missing := http.difference(self.remote_mcp_servers):
            denied.append(f"set sandbox.remote_mcp_servers for remote MCP: {', '.join(sorted(missing))}")
        if web_enabled and not self.allow_web_tools:
            denied.append("set sandbox.allow_web_tools for web providers")
        if denied:
            raise ToolError("Sandbox external tools require permission: " + ". ".join(denied) + ".")


class SandboxCleanupError(RuntimeError):
    """The runtime could not confirm the managed container was removed."""


def _probe(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=BACKGROUND_CREATION_FLAGS,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _docker(config: SandboxConfig) -> tuple[str, str] | None:
    executable = shutil.which(os.getenv("VERA_DOCKER_EXECUTABLE", "docker"))
    if executable is None:
        return None
    context = os.getenv("DOCKER_CONTEXT")
    host = None if context else os.getenv("DOCKER_HOST")
    if not host:
        host = _probe([executable, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"])
    if not host or not host.startswith(("unix:///", "npipe:////./pipe/")):
        return None
    info = _probe([executable, "info", "--format", "{{.OSType}} {{json .SecurityOptions}}"])
    if (
        not info
        or not info.startswith("linux ")
        or _probe([executable, "image", "inspect", "--format", "{{.Id}}", config.docker_image]) is None
    ):
        return None
    if "name=rootless" in info:
        user = "0:0"  # Container root maps to the unprivileged daemon user.
    else:
        user = f"{os.getuid()}:{os.getgid()}" if sys.platform == "linux" else "1000:1000"
    return executable, user


def _bubblewrap_args() -> list[str]:
    return [
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind-try",
        "/bin",
        "/bin",
        "--ro-bind-try",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--ro-bind-try",
        "/etc/ld.so.cache",
        "/etc/ld.so.cache",
        "--ro-bind-try",
        "/etc/alternatives",
        "/etc/alternatives",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/local/bin:/usr/bin:/bin",
        "--setenv",
        "HOME",
        "/tmp",
    ]


def _bubblewrap() -> str | None:
    if sys.platform != "linux":
        return None
    executable = shutil.which(os.getenv("VERA_BUBBLEWRAP_EXECUTABLE", "bwrap"))
    if executable and _probe([executable, *_bubblewrap_args(), "--chdir", "/tmp", "bash", "-c", "true"]) is not None:
        return executable
    return None


class _WorkspaceBubblewrap(BubblewrapEnvironment):
    def __init__(self, workspace: Path, config: SandboxConfig, executable: str):
        self._workspace = workspace
        self._mount_option = "--ro-bind" if config.workspace_access == "read-only" else "--bind"
        super().__init__(cwd=_WORKDIR, timeout=config.timeout, executable=executable, wrapper_args=_bubblewrap_args())

    def _workspace_args(self, cwd: str) -> list[str]:
        return [self._mount_option, str(self._workspace), _WORKDIR, "--chdir", _WORKDIR]


def _docker_mount(workspace: Path, access: str) -> str:
    fields = ["type=bind", f"source={workspace}", f"target={_WORKDIR}", "bind-recursive=disabled"]
    if access == "read-only":
        fields.append("readonly")
    buffer = io.StringIO()
    csv.writer(buffer).writerow(fields)
    return buffer.getvalue().rstrip("\r\n")


class _WorkspaceDocker(DockerEnvironment):
    def __init__(self, workspace: Path, config: SandboxConfig, executable: str, user: str):
        super().__init__(
            executable=executable,
            image=config.docker_image,
            cwd=_WORKDIR,
            timeout=config.timeout,
            env={"HOME": "/tmp"},
            run_args=[
                "--rm",
                "--init",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--user",
                user,
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "128",
                "--cpus",
                "2",
                "--memory",
                "1g",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=128m",
                "--mount",
                _docker_mount(workspace, config.workspace_access),
            ],
        )

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict:
        if self.container_id is None:
            raise ToolError("The Docker sandbox has closed. Start a new run to continue.")
        try:
            output = super().execute(action, cwd=_WORKDIR, timeout=timeout)
        except KeyboardInterrupt:
            self.cleanup()
            raise
        if output.get("extra", {}).get("exception_type") == "TimeoutExpired":
            self.cleanup()
        return output

    def cleanup(self) -> None:
        container = getattr(self, "container_id", None)
        if container is None:
            return
        try:
            result = subprocess.run(
                [self.config.executable, "rm", "--force", container],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                creationflags=BACKGROUND_CREATION_FLAGS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SandboxCleanupError(f"Unable to confirm removal of sandbox container {container}.") from error
        if result.returncode and "no such container" not in result.stderr.lower():
            raise SandboxCleanupError(f"Unable to confirm removal of sandbox container {container}.")
        self.container_id = None

    def __del__(self):
        # The session context owns cleanup and reports any failure to the caller.
        pass


@contextmanager
def open_runtime(sandbox: SandboxConfig, environment_config: dict) -> Iterator[tuple[Environment, str]]:
    """Open an execution mode and close managed resources when the agent run exits."""
    workspace = sandbox.workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise ToolError(f"Sandbox workspace is not a directory: {workspace}.")
    if sandbox.mode == SandboxMode.LOCAL:
        if sandbox.workspace_access == "read-only":
            raise ToolError("Read-only workspaces require --sandbox docker or --sandbox bubblewrap.")
        config = environment_config | {"environment_class": "local", "cwd": str(workspace), "timeout": sandbox.timeout}
        yield get_environment(config), "local (host access)"
        return
    if environment_config.get("environment_class") not in (None, "local"):
        raise ToolError("Select the execution environment with either sandbox.mode or environment.environment_class.")

    env = None
    mode = sandbox.mode
    if mode in {SandboxMode.AUTO, SandboxMode.BUBBLEWRAP} and (executable := _bubblewrap()):
        env = _WorkspaceBubblewrap(workspace, sandbox, executable)
        mode = SandboxMode.BUBBLEWRAP
    if env is None and mode in {SandboxMode.AUTO, SandboxMode.DOCKER} and (docker := _docker(sandbox)):
        try:
            env = _WorkspaceDocker(workspace, sandbox, *docker)
        except (OSError, subprocess.SubprocessError) as error:
            detail = getattr(error, "stderr", None) or type(error).__name__
            raise ToolError(f"Docker sandbox could not start: {detail.strip()}") from None
        mode = SandboxMode.DOCKER
    if env is None:
        guidance = []
        if mode in {SandboxMode.AUTO, SandboxMode.BUBBLEWRAP}:
            guidance.append("Use Linux or WSL with Bubblewrap and enabled user namespaces.")
        if mode in {SandboxMode.AUTO, SandboxMode.DOCKER}:
            guidance.append(
                f"Start a local Docker Linux engine and cache the image with docker pull {sandbox.docker_image}."
            )
        raise ToolError(
            f"Sandbox mode {mode.value!r} is unavailable. {' '.join(guidance)} For trusted projects use --sandbox local."
        )
    try:
        yield env, mode.value
    finally:
        env.cleanup()
