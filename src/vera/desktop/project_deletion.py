"""Scoped project removal previews; project source files are never deleted."""

import sqlite3
import time
from uuid import uuid4


def _catalog_identity(rows: list[dict]) -> list[dict]:
    """Keep deletion fences strict for content while ignoring view activation."""
    return [{key: value for key, value in row.items() if key != "active"} for row in rows]


class ProjectDeletion:
    """Bind one-use confirmations to an unchanged catalog and reject active conversations."""

    def __init__(self, service):
        self.service = service
        self.previews = {}

    def sessions(self, cwd):
        rows = {row["sessionId"]: row for row in self.service.metas()}
        rows.update({row["meta"]["sessionId"]: row["meta"] for row in self.service.store.list("delegated-session")})
        return sorted((row for row in rows.values() if row["cwd"] == cwd), key=lambda row: row["sessionId"])

    def invoke(self, method, args):
        with self.service.sessions.lock:
            rows = self.sessions(args["cwd"])
            if any(row["sessionId"] in self.service.sessions.running for row in rows):
                raise ValueError("请先停止项目中的运行任务，再移除项目。")
            if method == "previewSessionProjectDeletion":
                now = time.monotonic()
                self.previews = {key: value for key, value in self.previews.items() if value[0] > now}
                token = uuid4().hex
                self.previews[token] = (now + 600, args["cwd"], rows)
                return {
                    "cwd": args["cwd"],
                    "token": token,
                    "sessionCount": len(rows),
                    "archivedCount": sum(bool(row.get("archivedAt")) for row in rows),
                }
            preview = self.previews.pop(args["token"], None)
            if (
                not preview
                or preview[0] <= time.monotonic()
                or preview[1] != args["cwd"]
                or _catalog_identity(preview[2]) != _catalog_identity(rows)
            ):
                raise ValueError("项目会话已变化或确认已过期，请重新确认移除。")
            deleted, failed = [], []
            for row in rows:
                key = row["sessionId"]
                try:
                    (self.service.store.directory / "sessions" / (key + ".json")).unlink(missing_ok=True)
                    self.service.store.delete("session", key)
                    self.service.store.delete("delegated-session", key)
                except (OSError, sqlite3.Error) as error:
                    failed.append({"sessionId": key, "error": str(error)})
                else:
                    deleted.append(key)
            self.service.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            return {"deleted": deleted, "failed": failed}
