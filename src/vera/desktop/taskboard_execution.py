"""Bridge explicitly selected upstream issues to ordinary, inspectable desktop Agent runs."""

import threading
import time
from urllib.parse import quote

import requests


class TaskboardExecution:
    """Keep execution receipts locally and update the upstream board through its versioned HTTP API.

    Starting a run is explicit; merely opening the board never dispatches tasks.
    Success means ready for human review, not that the issue has been accepted.
    """

    def __init__(self, desktop):
        self.desktop = desktop
        self.lock = threading.RLock()
        self.sync_lock = threading.RLock()
        self.stopping = threading.Event()
        self.watcher = None
        self.pending = set()

    def request(self, method: str, path: str, **kwargs) -> dict:
        """Use only this profile's owned loopback capability; surface upstream failures."""
        address = self.desktop.taskboard.status()["url"]
        if not address:
            raise ValueError("请先启动任务面板。")
        response = requests.request(method, address + "api/" + path, timeout=5, **kwargs)
        if not response.ok:
            raise ValueError(f"Taskboard HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def snapshot(self) -> dict:
        """Return current issues and durable run history; recover interrupted runs after restart."""
        with self.lock:
            runs = self.desktop.store.list("taskboard-run")
        for run in runs:
            if run["status"] == "running" and run["sessionId"] not in self.desktop.sessions.running:
                self.finish(run)
        return {
            "tasks": self.request("GET", "tasks")["tasks"],
            "runs": sorted(self.desktop.store.list("taskboard-run"), key=lambda row: row["startedAt"], reverse=True),
        }

    def start(self, args: dict) -> dict:
        """Validate task version, workspace, model and permission before accepting one execution.

        Confirm mode keeps ordinary desktop approval gates. Yolo requires the
        caller's explicit selection; neither mode introduces an execution budget.
        """
        with self.lock:
            task_id = quote(args["taskId"], safe="")
            task = self.request("GET", "tasks/" + task_id)["task"]
            if task["version"] != args["version"]:
                raise ValueError("任务已更新，请刷新后重试。")
            if task.get("archivedAt") or task["status"] in {"done", "canceled"}:
                raise ValueError("已归档、完成或取消的任务不能启动。")
            if any(
                row["taskId"] == task["id"] and row["status"] == "running"
                for row in self.desktop.store.list("taskboard-run")
            ):
                raise ValueError("这个任务已在执行，请打开执行对话。")
            if task.get("developmentContext"):
                raise ValueError("此任务绑定了分支或 worktree，请先在对应项目对话中执行。")
            permission = args.get("permissionPolicy", "confirm")
            if permission not in {"confirm", "yolo"}:
                raise ValueError("任务执行仅支持确认模式或明确选择的完全通过模式。")
            if not args.get("provider") or not args.get("modelId"):
                raise ValueError("请选择执行模型。")
            if not self.desktop.providers.definition({"provider": args["provider"], "modelId": args["modelId"]}):
                raise ValueError("执行模型已被移除，请重新选择。")
            value = self.desktop.store.create_session(args)
            key = value["meta"]["sessionId"]
            value["meta"]["name"] = f"{task['identifier']} · {task['title']}"
            value["permissionPolicy"] = permission
            value["selections"]["runMode"] = "normal"
            try:
                self.desktop.sessions.config(value)
                self.request("PATCH", "tasks/" + task_id, json={"version": task["version"], "status": "in_progress"})
            except Exception:
                self.desktop.store.delete("session", key)
                (self.desktop.store.directory / "sessions" / f"{key}.json").unlink(missing_ok=True)
                raise
            self.desktop.save_session(value)
            run = {
                "sessionId": key,
                "taskId": task["id"],
                "title": value["meta"]["name"],
                "status": "running",
                "startedAt": int(time.time() * 1000),
                "error": None,
            }
            self.desktop.store.save("taskboard-run", key, run)
            try:
                self.desktop.sessions.prompt(
                    key,
                    f"执行任务 {task['identifier']}：{task['title']}\n\n{task['description']}\n\n"
                    "完成后说明结果与验证证据；如有阻塞请如实说明。任务状态由桌面端回写，不要自行修改看板。",
                )
            except Exception as error:
                run["error"] = str(error)
                self.finish(run)
                raise
            self.desktop.events.emit("onSessionCatalogChanged", {"revision": key, "complete": True})
            self.pending.add(key)
            if not self.watcher or not self.watcher.is_alive():
                self.watcher = threading.Thread(target=self.watch, daemon=True)
                self.watcher.start()
            return run

    def finish(self, run: dict) -> None:
        """Persist the real terminal outcome, then retry safe board synchronization separately."""
        with self.lock:
            current = self.desktop.store.get("taskboard-run", run["sessionId"], run)
            if current["status"] != "running":
                return
            value = self.desktop.store.get("session", run["sessionId"], {})
            receipt = value.get("lastRunResult") or {}
            status = receipt.get("exit_status", "Interrupted")
            run.update(
                status="completed" if status == "Submitted" and not run.get("error") else "error",
                endedAt=int(time.time() * 1000),
                output=str(receipt.get("submission", ""))[:16000],
                error=run.get("error") or (None if status == "Submitted" else status),
                synced=False,
            )
            self.desktop.store.save("taskboard-run", run["sessionId"], run)
            self.pending.discard(run["sessionId"])
        self.sync(run)

    def sync(self, run: dict) -> None:
        """Write a receipt comment once and never overwrite a user's later task state."""
        if not run or run["status"] == "running":
            raise ValueError("只能回写已结束的执行记录。")
        # Serialize only board writes; observation and new dispatches remain available.
        with self.sync_lock:
            current = self.desktop.store.get("taskboard-run", run["sessionId"], run)
            self._sync(current)

    def _sync(self, run: dict) -> None:
        """Synchronize a freshly read receipt while holding only the board-write lock."""
        path = "tasks/" + quote(run["taskId"], safe="")
        try:
            task = self.request("GET", path)["task"]
            if task.get("archivedAt"):
                raise ValueError("任务已归档；执行记录仍保存在 VERA。")
            if not run.get("commented"):
                self.request(
                    "POST",
                    path + "/comments",
                    json={
                        "body": f"VERA 执行：{run['status']}\n对话：{run['sessionId']}\n"
                        + (run.get("error") or run.get("output") or "请打开 VERA 执行对话查看结果。")
                    },
                )
                run["commented"] = True
                self.desktop.store.save("taskboard-run", run["sessionId"], run)
            if task["status"] == "in_progress":
                self.request(
                    "PATCH",
                    path,
                    json={
                        "version": task["version"],
                        "status": "in_review" if run["status"] == "completed" else "blocked",
                    },
                )
            run.update(synced=True, syncError=None)
        except (requests.RequestException, ValueError) as error:
            run["syncError"] = str(error)
        self.desktop.store.save("taskboard-run", run["sessionId"], run)

    def watch(self) -> None:
        """Observe the normal desktop worker lifecycle without changing its execution loop."""
        while not self.stopping.wait(0.3):
            with self.lock:
                runs = [self.desktop.store.get("taskboard-run", key) for key in self.pending]
            for run in runs:
                if run["status"] == "running" and run["sessionId"] not in self.desktop.sessions.running:
                    self.finish(run)

    def close(self) -> None:
        """Stop observing on desktop shutdown; pending receipts recover on the next board load."""
        self.stopping.set()
        if self.watcher:
            self.watcher.join(timeout=6)
