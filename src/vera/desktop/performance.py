"""Collect task timings and bounded diagnostic categories without retaining user content."""

import json
import math
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from statistics import mean


class TaskObservation:
    """Observe worker frames outside the Agent Loop; persist one receipt when the task settles."""

    def __init__(self, usage, identifier: str, meta: dict, started: float, timestamp: int, has_history: bool = False):
        self.usage, self.identifier, self.meta = usage, identifier, meta
        self.started, self.timestamp = started, timestamp
        self.first_response = None
        self.model_request_ms = None
        self.runtime_ready_ms = None
        self.retries = 0
        self.model_issue = False
        self.tools = {}
        self.errors = Counter()
        self.has_history = has_history

    def observe(self, frame: dict) -> None:
        """Count effective output, actual retry attempts, and completed tool results only."""
        kind = frame["type"]
        now = time.monotonic()
        if not frame.get("parentToolCallId"):
            if kind == "tools_ready" and self.runtime_ready_ms is None:
                self.runtime_ready_ms = (now - self.started) * 1000
            if kind == "model_request" and self.model_request_ms is None:
                self.model_request_ms = (now - self.started) * 1000
        if kind == "model_request":
            self.usage.begin_request(
                frame["id"],
                self.meta["sessionId"],
                self.identifier,
                bool(frame.get("parentToolCallId")),
                self.has_history,
            )
        elif kind == "retry":
            self.retries += 1
            self.model_issue = True
            if frame.get("reason") == "format":
                self.errors["FormatRetry"] += 1
        elif kind == "model_failure":
            self.model_issue = True
            self.errors[frame["category"]] += 1
        elif kind == "tool_start":
            self.tools[frame["toolCallId"]] = {"name": frame["toolName"], "started": now}
        elif kind == "tool_end":
            tool = self.tools.get(frame["toolCallId"])
            if tool and "durationMs" not in tool:
                result = frame["result"]
                tool.update(durationMs=(now - tool["started"]) * 1000, failed=bool(result.get("returncode", 0)))
                if tool["failed"]:
                    self.errors["ToolError"] += 1
        if self.first_response is None and not frame.get("parentToolCallId"):
            if kind == "stream_delta":
                update = frame["update"]
                effective = bool(update.get("delta")) or update.get("type") == "toolcall_start"
            else:
                message = frame.get("message", {}) if kind == "message" else {}
                effective = bool(message.get("content") or message.get("extra", {}).get("actions"))
            if effective:
                self.first_response = (now - self.started) * 1000

    def finish(self, status: str) -> None:
        """Record technical completion separately from failures and user cancellation."""
        if status not in {"Submitted", "Cancelled"} and not self.errors:
            self.errors[status] += 1
        reference = self.meta.get("model") or {}
        self.usage.performance.record(
            self.identifier,
            self.timestamp,
            self.meta["cwd"],
            reference.get("provider", ""),
            reference.get("modelId", "unknown"),
            {
                "status": status,
                "firstResponseMs": self.first_response,
                "runtimeReadyMs": self.runtime_ready_ms,
                "modelRequestMs": self.model_request_ms,
                "providerWaitMs": self.first_response - self.model_request_ms
                if self.first_response is not None and self.model_request_ms is not None
                else None,
                "normalResponse": not self.model_issue,
                "retries": self.retries,
                "tools": [
                    {key: value for key, value in tool.items() if key != "started"} for tool in self.tools.values()
                ],
                "errors": dict(self.errors),
            },
        )


class PerformanceStats:
    """Aggregate completed task receipts using the same date, project and model filters as usage."""

    def __init__(self, store):
        self.store = store
        with store.lock, closing(sqlite3.connect(store.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS desktop_performance (id TEXT PRIMARY KEY, timestamp INTEGER NOT NULL, "
                "project TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS performance_time ON desktop_performance(timestamp)")

    def record(self, identifier: str, timestamp: int, project: str, provider: str, model: str, payload: dict) -> None:
        """Insert an idempotent task receipt; no prompts, tool arguments or raw errors are stored."""
        with self.store.lock, closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO desktop_performance VALUES (?,?,?,?,?,?)",
                (identifier, timestamp, project, provider, model, json.dumps(payload)),
            )

    def query(self, clauses: list[str], parameters: list) -> dict:
        """Use stable successful tasks for response timing and a 5%-per-tail trimmed retry mean at n >= 20.

        All terminal outcomes contribute to completion rate. Cancelled tasks are
        counted separately. Trimmed retry observations remain in the raw mean.
        """
        with self.store.lock, closing(sqlite3.connect(self.store.path)) as db:
            tasks = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM desktop_performance" + (" WHERE " + " AND ".join(clauses) if clauses else ""),
                    parameters,
                )
            ]
        statuses = Counter(task["status"] for task in tasks)
        responses = [
            task["firstResponseMs"]
            for task in tasks
            if task["status"] == "Submitted"
            and task["normalResponse"]
            and task["firstResponseMs"] is not None
            and math.isfinite(task["firstResponseMs"])
            and task["firstResponseMs"] >= 0
        ]
        retries = sorted(task["retries"] for task in tasks if isinstance(task["retries"], int) and task["retries"] >= 0)
        trim = len(retries) // 20 if len(retries) >= 20 else 0
        cleaned = retries[trim:-trim] if trim else retries
        tools = defaultdict(lambda: {"calls": 0, "failures": 0, "totalMs": 0, "timedCalls": 0})
        errors = Counter()
        for task in tasks:
            errors.update(task["errors"])
            for tool in task["tools"]:
                row = tools[tool["name"]]
                row["calls"] += 1
                if "durationMs" in tool:
                    row["timedCalls"] += 1
                    row["totalMs"] += tool["durationMs"]
                    row["failures"] += int(tool["failed"])
        return {
            "tasks": len(tasks),
            "completed": statuses["Submitted"],
            "cancelled": statuses["Cancelled"],
            "failed": len(tasks) - statuses["Submitted"] - statuses["Cancelled"],
            "completionRate": statuses["Submitted"] / len(tasks) if tasks else None,
            "firstResponseMeanMs": mean(responses) if responses else None,
            "firstResponseSamples": len(responses),
            "firstResponseExcluded": len(tasks) - len(responses),
            "retryMean": mean(cleaned) if cleaned else None,
            "retryRawMean": mean(retries) if retries else None,
            "retrySamples": len(cleaned),
            "retryExcluded": len(retries) - len(cleaned),
            "tools": [
                {"name": name, **row, "meanMs": row["totalMs"] / row["timedCalls"] if row["timedCalls"] else None}
                for name, row in sorted(tools.items(), key=lambda item: (-item[1]["calls"], item[0]))[:5]
            ],
            "errors": [{"name": name, "count": count} for name, count in errors.most_common(5)],
        }
