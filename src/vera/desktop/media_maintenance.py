"""Preview and reversibly deduplicate screenshots in the authoritative desktop session store."""

import json
import re
import time
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

from vera.desktop.media_codec import encode_images
from vera.evolution.process import read_json, write_json


def fingerprint(value: dict) -> str:
    """Fence content changes while allowing the view to close or reopen."""
    content = deepcopy(value)
    content["meta"].pop("active", None)
    return sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


class MediaMaintenance:
    """Keep originals, losslessly deduplicate image bytes, and restore only unchanged sessions."""

    methods = {
        "getSessionMediaMaintenance",
        "startSessionMediaPreview",
        "getSessionMediaJob",
        "cancelSessionMediaJob",
        "getSessionMediaTransaction",
        "startSessionMediaCompaction",
        "startSessionMediaRestore",
    }

    def __init__(self, service):
        self.service = service
        self.store = service.store

    def session(self, path: str) -> dict:
        meta = next((row for row in self.service.metas() if row["sessionFile"] == path), None)
        if meta is None:
            raise ValueError("请选择当前应用中已有的会话。")
        return self.service.idle_session(meta["sessionId"])

    def invoke(self, method, args):
        with self.service.sessions.lock, self.store.lock:
            if method == "getSessionMediaTransaction":
                return self.store.get("media-transaction", args["requestId"])
            if method in {"getSessionMediaJob", "cancelSessionMediaJob"}:
                job = self.store.get("media-job", args["jobId"])
                if job is None:
                    raise ValueError("截图整理任务不存在。")
                return job  # Operations complete atomically before returning; cancellation cannot undo publication.
            if method == "getSessionMediaMaintenance":
                value = self.session(args["sessionFile"])
                return self.store.get("media-latest", value["meta"]["sessionId"])
            if method == "startSessionMediaRestore":
                record = self.store.get("media-transaction", args["compactionRequestId"])
                if not record or record["kind"] != "compact" or record["phase"] != "complete":
                    raise ValueError("没有可恢复的截图整理备份。")
                value = self.session(record["sessionFile"])
                backup = read_json(self.store.directory / "media-backups" / f"{record['requestId']}.json")
                # Also accept backups from the original layout, whose digest included view state.
                legacy_hash = sha256(json.dumps(backup, sort_keys=True).encode()).hexdigest()
                if record["backupHash"] not in {fingerprint(backup), legacy_hash}:
                    raise ValueError("截图整理备份校验失败；已保留当前会话和备份。")
                if fingerprint(value) != fingerprint(backup):
                    raise ValueError("整理后会话已有新内容；已保留备份，不能覆盖后续对话。")
                backup["meta"]["active"] = value["meta"]["active"]
                return self.publish(args, value, backup, "restore", record)
            value = self.session(args["sessionFile"])
            if method == "startSessionMediaCompaction":
                if args["expectedHash"] != fingerprint(value):
                    raise ValueError("会话在预览后已变化，请重新预览。")
                return self.publish(args, value, value, "compact")
            blobs = {}
            encoded = encode_images(value, blobs)
            before = len(json.dumps(value).encode())
            after = len(json.dumps(encoded).encode()) + sum(map(len, blobs.values()))
            preview = {
                "supported": True,
                "sourceVersion": 1,
                "sourceHash": fingerprint(value),
                "sourceFingerprint": fingerprint(value),
                "sessionId": value["meta"]["sessionId"],
                "fileBytes": before,
                "projectedFileBytes": after,
                "imageCount": sum(len(row.get("images", [])) for row in value["messages"]),
                "uniqueImages": len(blobs),
                "originalImageBytes": sum(map(len, blobs.values())),
                "backupBytes": before,
                "additionalPeakBytes": before + after,
                "invalidLines": 0,
                "skippedImages": 0,
            }
            if not blobs or after >= before or self.store.get("media-latest", value["meta"]["sessionId"]):
                preview["reason"] = "no-benefit"
            return self.job("preview", value["meta"]["sessionFile"], result=preview)

    def job(self, kind, path, **fields):
        now = int(time.time() * 1000)
        job = {
            "jobId": uuid4().hex,
            "kind": kind,
            "sessionFile": path,
            "status": "completed",
            "processedBytes": 0,
            "totalBytes": 0,
            "createdAt": now,
            "updatedAt": now,
            **fields,
        }
        self.store.save("media-job", job["jobId"], job)
        return job

    def publish(self, args, current, replacement, kind, original=None):
        """Save the complete original before the atomic SQLite layout change; never delete backups."""
        request = args["requestId"]
        if args.get("confirmed") is not True or not re.fullmatch(r"[a-fA-F0-9-]{16,64}", request):
            raise ValueError("请明确确认截图整理或恢复。")
        if previous := self.store.get("media-transaction", request):
            return self.store.get("media-job", previous["operationId"])
        key = current["meta"]["sessionId"]
        backup = self.store.directory / "media-backups" / f"{request}.json"
        backup.parent.mkdir(exist_ok=True)
        write_json(backup, current)
        now = int(time.time() * 1000)
        record = {
            "version": 1,
            "requestId": request,
            "kind": kind,
            "sessionFile": current["meta"]["sessionFile"],
            "expectedHash": fingerprint(current),
            "phase": "complete",
            "backup": str(backup),
            "candidate": "",
            "createdAt": now,
            "updatedAt": now,
            "backupHash": fingerprint(current),
            "outputHash": fingerprint(replacement),
        }
        if original:
            record["originalRequestId"] = original["requestId"]
        job = self.job(kind, record["sessionFile"], requestId=request)
        record["operationId"] = job["jobId"]
        job["transaction"] = record
        self.store.image_layout(
            key,
            replacement,
            enabled=kind == "compact",
            records=(
                ("media-job", job["jobId"], job),
                ("media-transaction", request, record),
                ("media-latest", key, record if kind == "compact" else None),
            ),
        )
        return job
