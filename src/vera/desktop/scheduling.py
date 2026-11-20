"""Map desktop schedules to the existing persistent scheduler and daemon."""

from datetime import datetime, timezone

from vera.scheduler.engine import start_service
from vera.scheduler.store import JobStore


class ScheduledTasks:
    """Keep display drafts with real JobStore identities; never fabricate runs."""

    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.jobs = JobStore(self.store.directory / "scheduler")

    def snapshot(self):
        tasks = []
        for draft in self.store.list("scheduled"):
            job = self.jobs.get(draft["id"])
            tasks.append(draft | {"enabled": job["state"] == "scheduled", "nextRunAt": job.get("next_run_at")})
        runs = []
        for row in self.jobs.history():
            result = row.get("result") or {}
            runs.append(
                {
                    "id": row["id"],
                    "taskId": row["job_id"],
                    "sessionId": None,
                    "status": {"completed": "completed", "running": "running", "cancelled": "aborted"}.get(
                        row["status"], "error"
                    ),
                    "errorCode": None if row["status"] == "completed" else row["status"],
                    "startedAt": row.get("started_at") or row.get("scheduled_at"),
                    "endedAt": row.get("ended_at"),
                    "output": result.get("summary", ""),
                }
            )
        return {"tasks": tasks, "runs": runs}

    def invoke(self, method, args):
        if method == "getScheduledTasks":
            return self.snapshot()
        if method == "saveScheduledTask":
            draft = args["draft"]
            if draft["permissionMode"] != "yolo":
                raise ValueError(
                    "Unattended tasks require explicit yolo permission; interactive approval cannot run in the background."
                )
            if draft["sessionMode"] != "perRun":
                raise ValueError("Scheduled tasks currently use an independent context per run.")
            schedule = draft.get("schedule") or {}
            cadence = draft["cadence"]
            if cadence == "weekly":
                days = ",".join(str((day + 1) % 7) for day in schedule.get("weekdays", [schedule["weekday"]]))
                expression = f"{schedule['minute']} {schedule['hour']} * * {days}"
            elif cadence == "daily":
                expression = f"{schedule['minute']} {schedule['hour']} * * *"
            elif cadence == "interval":
                expression = f"every {schedule['intervalMinutes']}m"
            else:
                expression = "every 1h"
            model = None
            if draft.get("modelRef"):
                provider, _, model_id = draft["modelRef"].partition("/")
                model = {"provider": provider, "modelId": model_id}
            config = self.service.sessions.config(
                {
                    "meta": {
                        "sessionId": "scheduled",
                        "cwd": draft["workspacePath"],
                        "model": model,
                        "thinkingLevel": draft.get("thinkingLevel", "off")
                        if draft.get("thinkingLevel") != "inherit"
                        else "off",
                    },
                    "permissionPolicy": "yolo",
                    "selections": {},
                }
            )
            config["agent"]["mode"] = "yolo"
            spec = {
                "name": draft["title"],
                "prompt": draft["prompt"],
                "schedule": expression,
                "timezone": draft.get("timezone", "Asia/Shanghai"),
                "workspace": draft["workspacePath"],
                "config": config,
            }
            now = datetime.now(timezone.utc).isoformat()
            key = args.get("id")
            job = self.jobs.update(key, spec) if key else self.jobs.create(spec)
            self.jobs.control(job["id"], "pause")
            value = draft | {"id": job["id"], "enabled": False, "createdAt": now, "updatedAt": now}
            self.store.save("scheduled", job["id"], value)
        else:
            key, action = args["id"], args["action"]
            if action == "enable" and self.store.get("scheduled", key)["cadence"] == "manual":
                raise ValueError("Manual tasks run only through Run now.")
            self.jobs.control(key, {"enable": "resume", "disable": "pause"}.get(action, action))
            if action == "remove":
                self.store.delete("scheduled", key)
            elif action in {"enable", "run"}:
                start_service(self.jobs.directory)
        return self.snapshot()
