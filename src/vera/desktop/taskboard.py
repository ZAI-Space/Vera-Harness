"""Own a local, isolated dashi-taskboard service without modifying its source or the host app."""

import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import requests

from vera import global_config_dir
from vera.evolution.process import _kill_tree

TASKBOARD_REVISION = "bc25451c5c49a14abb6c4e8250b62c626b007f8a"
TASKBOARD_REPOSITORY = "https://github.com/chuspeeism/dashi-taskboard"


class TaskboardService:
    """Launch the upstream HTTP app on an owned loopback port with separate data and credentials.

    Only an explicitly opened board starts the process. The upstream native
    launchers/injectors are not used. Node and the built source are prerequisites.
    """

    def __init__(self, store):
        self.store = store
        self.process = None
        self.url = None
        self.lock = threading.RLock()

    def source(self) -> Path | None:
        """Resolve an explicit installation or the profile's versioned setup descriptor."""
        if directory := os.environ.get("VERA_TASKBOARD_HOME"):
            return Path(directory).expanduser().resolve()
        descriptor = global_config_dir / "integrations/dashi-taskboard/current.json"
        if descriptor.is_file():
            try:
                value = json.loads(descriptor.read_text(encoding="utf-8-sig"))
                directory = value.get("directory") if isinstance(value, dict) else None
                return Path(directory) if isinstance(directory, str) and directory else None
            except (OSError, ValueError):
                return None
        return None

    def status(self) -> dict:
        """Return public integration state; only the running iframe receives its capability URL."""
        source = self.source()
        installed = bool(
            source and (source / "server/index.mjs").is_file() and (source / "dist/web/index.html").is_file()
        )
        running = self.process is not None and self.process.poll() is None
        return {
            "installed": installed,
            "running": running,
            "url": self.url if running else None,
            "repository": TASKBOARD_REPOSITORY,
            "revision": TASKBOARD_REVISION,
            "nodeAvailable": shutil.which("node") is not None,
        }

    def start(self) -> dict:
        """Start only the installed upstream service, keeping all task data under this desktop profile."""
        with self.lock:
            status = self.status()
            if status["running"]:
                return status
            if not status["installed"] or not status["nodeAvailable"]:
                raise ValueError("请先安装 Taskboard 与 Node.js，再启动任务面板。")
            source = self.source()
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            token = secrets.token_hex(24)
            directory = self.store.directory / "taskboard"
            directory.mkdir(exist_ok=True)
            environment = os.environ | {
                "CODEX_TASKBOARD_HOST": "127.0.0.1",
                "CODEX_TASKBOARD_PORT": str(port),
                "CODEX_TASKBOARD_DATA_DIR": str(directory),
                "CODEX_TASKBOARD_INSTANCE_TOKEN": token,
                "CODEX_TASKBOARD_INSTANCE_SECRET": secrets.token_hex(32),
                "CODEX_HOME": str(directory / "agent-profile"),
            }
            with (directory / "server.log").open("a", encoding="utf-8") as log:
                self.process = subprocess.Popen(
                    [shutil.which("node"), str(source / "server/index.mjs")],
                    cwd=source,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
            self.url = f"http://127.0.0.1:{port}/{token}/"
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self.process.poll() is None:
                try:
                    response = requests.get(self.url, timeout=0.5)
                    if response.status_code == 200:
                        return self.status()
                except (requests.ConnectionError, requests.Timeout):
                    pass
                time.sleep(0.1)
            try:
                self.close()
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ValueError("Taskboard 启动失败且进程未能退出，请检查本机 Taskboard 日志。") from error
            raise ValueError("Taskboard 启动失败，请检查本机 Taskboard 日志与安装依赖。")

    def close(self) -> dict:
        """Stop the owned process tree; saved tasks remain in the profile database."""
        with self.lock:
            if self.process and self.process.poll() is None:
                _kill_tree(self.process.pid)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Retain ownership if escalation also fails; never hide a live child.
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process, self.url = None, None
            return self.status()
