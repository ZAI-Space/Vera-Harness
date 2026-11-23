"""Optional upstream integration test; install with setup-taskboard.ps1 and set VERA_TASKBOARD_HOME."""

import os
import shutil
from urllib.parse import urlsplit

import pytest
import requests

from vera.desktop.store import DesktopStore
from vera.desktop.taskboard import TaskboardService


@pytest.mark.skipif(
    not os.getenv("VERA_TASKBOARD_HOME") or not shutil.which("node"),
    reason="Requires an installed upstream Taskboard and Node",
)
def test_upstream_board_creates_tasks_persists_and_stops_owned_process(tmp_path):
    board = TaskboardService(DesktopStore(tmp_path))
    try:
        status = board.start()
        assert status["running"]
        address = status["url"]
        assert requests.get(address, timeout=5).status_code == 200
        root = urlsplit(address)
        assert requests.get(f"{root.scheme}://{root.netloc}/api/tasks", timeout=5).status_code != 200
        response = requests.post(address + "api/tasks", json={"title": "VERA integration acceptance"}, timeout=5)
        assert response.status_code == 201, response.text
        task = response.json()["task"]
        assert requests.get(address + "api/tasks/" + task["id"], timeout=5).json()["task"]["title"] == task["title"]
        process = board.process
        assert not board.close()["running"] and process.poll() is not None
        restored = board.start()
        assert restored["url"] != address
        assert (
            requests.get(restored["url"] + "api/tasks/" + task["id"], timeout=5).json()["task"]["title"]
            == task["title"]
        )
    finally:
        board.close()
