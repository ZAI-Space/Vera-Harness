"""Isolate the entire historical optimizer process, including evolved Python code.

Tool-only isolation cannot protect a verifier from a self-modified runtime. Docker
or Bubblewrap therefore wraps the Python process itself. Explicit local mode is
for trusted development and offers no host filesystem/security boundary.
"""

import os
import subprocess
import sys
from pathlib import Path

from minisweagent.environments.sandbox import SandboxConfig, _bubblewrap, _bubblewrap_args, _docker, _docker_mount
from minisweagent.evolution.config import EvolutionConfig, EvolutionError


def select_runtime(config: EvolutionConfig) -> dict:
    """Resolve auto to an available backend; never silently downgrade to local."""
    if config.sandbox == "local":
        return {"mode": "local"}
    if config.sandbox in {"auto", "bubblewrap"} and (executable := _bubblewrap()):
        return {"mode": "bubblewrap", "executable": executable}
    if config.sandbox in {"auto", "docker"} and (runtime := _docker(SandboxConfig(docker_image=config.docker_image))):
        executable, user = runtime
        image = subprocess.check_output(
            [executable, "image", "inspect", "--format", "{{.Id}}", config.docker_image],
            text=True,
        ).strip()
        return {"mode": "docker", "executable": executable, "user": user, "image": image}
    raise EvolutionError(
        "No complete optimizer sandbox is available. Prepare the configured Docker runtime image, "
        "install Bubblewrap on Linux, or explicitly choose sandbox: local for trusted development."
    )


def stop_container(runtime: dict, name: str) -> None:
    """Remove only the experiment-owned container, checking that cleanup succeeded."""
    executable = runtime["executable"]
    removed = subprocess.run([executable, "rm", "--force", name], capture_output=True, timeout=30)
    if removed.returncode:
        listed = subprocess.check_output(
            [executable, "ps", "-aq", "--filter", f"name=^/{name}$"], text=True, timeout=15
        )
        if listed.strip():
            raise EvolutionError(f"Could not remove optimizer container {name}.")


def optimizer_command(
    runtime: dict,
    *,
    workspace: Path,
    optimizer: Path,
    artifacts: Path,
    worker: Path,
    name: str,
    env: dict,
) -> tuple[list[str], dict]:
    """Mount candidate writable, historical optimizer read-only, and no evaluation data.

    Only explicitly configured provider credential variables reach isolated workers.
    Runtime image is pinned by content ID; registry tags cannot replace it mid-run.
    """
    mode = runtime["mode"]
    if mode == "local":
        return [sys.executable, str(worker), str(artifacts / "request.json")], env
    forwarded = {
        key: value
        for key, value in env.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP"} or key in runtime["credential_env"]
    }
    forwarded |= {
        "PYTHONPATH": "/optimizer/src",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MSWEA_CONFIGURED": "true",
        "MSWEA_GLOBAL_CONFIG_DIR": "/tmp/vera-config",
    }
    if mode == "docker":
        command = [
            runtime["executable"],
            "run",
            "--rm",
            "--init",
            "--pull",
            "never",
            "--name",
            name,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            runtime["user"],
            "--pids-limit",
            "128",
            "--memory",
            "2g",
            "--cpus",
            "2",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m",
            "--workdir",
            "/workspace",
        ]
        for host, guest, access in [
            (workspace, "/workspace", "read-write"),
            (optimizer, "/optimizer", "read-only"),
            (artifacts, "/artifacts", "read-write"),
            (worker, "/worker.py", "read-only"),
        ]:
            command += ["--mount", _docker_mount(host, access).replace("target=/workspace", f"target={guest}")]
        for key in forwarded:
            if key not in {"PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP"}:
                command += ["--env", key]
        return [*command, runtime["image"], "python", "/worker.py", "/artifacts/request.json"], os.environ | forwarded
    arguments = _bubblewrap_args()
    arguments.remove("--clearenv")
    arguments += [
        "--share-net",
        "--ro-bind-try",
        "/etc/resolv.conf",
        "/etc/resolv.conf",
        "--ro-bind-try",
        "/etc/ssl",
        "/etc/ssl",
    ]
    for prefix in sorted({sys.prefix, sys.base_prefix}):
        if not Path(prefix).is_relative_to(Path("/usr")):
            arguments += ["--ro-bind", prefix, prefix]
    arguments += [
        "--setenv",
        "PATH",
        f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin",
        "--bind",
        str(workspace),
        "/workspace",
        "--ro-bind",
        str(optimizer),
        "/optimizer",
        "--bind",
        str(artifacts),
        "/artifacts",
        "--ro-bind",
        str(worker),
        "/worker.py",
        "--chdir",
        "/workspace",
    ]
    return [runtime["executable"], *arguments, sys.executable, "/worker.py", "/artifacts/request.json"], forwarded
