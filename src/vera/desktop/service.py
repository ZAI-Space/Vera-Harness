"""Desktop request routing, session catalog and safe configuration projections."""

import html
import json
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from vera.desktop.events import EventBus
from vera.desktop.providers import Providers
from vera.desktop.sessions import Sessions
from vera.desktop.store import DesktopStore
from vera.terminal.files import ProjectFiles


class DesktopService:
    """Map the existing frontend's methods to actual VERA module operations.

    Unsupported inherited SDK methods fail explicitly. Nothing is dynamically
    imported or dispatched from a client method/path. The transport is loopback,
    bearer-authenticated and owned by the external desktop launcher.
    """

    def __init__(self, directory: Path, config: dict | None = None, *, context_directory: Path | None = None):
        from vera.channels.credentials import private_directory
        from vera.desktop.capabilities import Capabilities
        from vera.desktop.lan import LanService
        from vera.desktop.taskboard import TaskboardService
        from vera.desktop.usage import UsageStats
        from vera.user_context import UserContext

        self.store = DesktopStore(private_directory(directory))
        self.events = EventBus()
        self.providers = Providers(self.store)
        self.user_context = UserContext(context_directory or self.store.directory / "user-context")
        self.sessions = Sessions(self.store, self.providers, self.events, config)
        self.sessions.user_context_directory = self.user_context.directory
        self.usage = UsageStats(self.store)
        from vera.desktop.web import WebSettings

        self.web = WebSettings(self.store)
        self.taskboard = TaskboardService(self.store)
        from vera.desktop.taskboard_execution import TaskboardExecution

        self.taskboard_execution = TaskboardExecution(self)
        self.sessions.usage = self.usage
        from vera.desktop.project_deletion import ProjectDeletion

        self.project_deletion = ProjectDeletion(self)
        from vera.desktop.media_maintenance import MediaMaintenance

        self.media_maintenance = MediaMaintenance(self)
        self.capabilities = Capabilities(self)
        self.lan = LanService(self)
        from vera.desktop.remote_channels import RemoteChannels

        self.remote_channels = RemoteChannels(self)

    def metas(self) -> list[dict]:
        return [value["meta"] for value in self.store.list("session")]

    def save_session(self, value: dict):
        """Keep catalog counts aligned when configuration or display history changes."""
        value["meta"]["messageCount"] = len(value["messages"])
        self.store.save("session", value["meta"]["sessionId"], value)

    def idle_session(self, key: str) -> dict:
        if self.sessions.get(key)["meta"].get("parentSessionId"):
            raise ValueError("Subagent inspection is read-only. Continue in the parent conversation.")
        if key in self.sessions.running:
            raise ValueError("Stop this session before changing its configuration or history.")
        return self.sessions.get(key)

    def invoke(self, method: str, args: dict | None = None):
        """Validate JSON method arguments and return the desktop DTO or a visible error."""
        args = args or {}
        if not isinstance(args, dict):
            raise ValueError("Expected an argument object.")
        if method in self.capabilities.methods:
            return self.capabilities.invoke(method, args)
        key = args.get("sessionId")
        if method in self.media_maintenance.methods:
            return self.media_maintenance.invoke(method, args)
        if method in {"previewSessionProjectDeletion", "deleteSessionProject"}:
            return self.project_deletion.invoke(method, args)
        if method == "getTaskboardStatus":
            return self.taskboard.status()
        if method == "startTaskboard":
            return self.taskboard.start()
        if method == "stopTaskboard":
            if any(row["status"] == "running" for row in self.store.list("taskboard-run")):
                raise ValueError("请先在执行对话中停止任务，再停止看板服务。")
            return self.taskboard.close()
        if method == "getTaskboardExecution":
            return self.taskboard_execution.snapshot()
        if method == "runTaskboardTask":
            return self.taskboard_execution.start(args)
        if method == "syncTaskboardRun":
            with self.taskboard_execution.lock:
                self.taskboard_execution.sync(self.store.get("taskboard-run", args["sessionId"]))
                return self.taskboard_execution.snapshot()
        if method == "getUserContext":
            return {"entries": self.user_context.entries(), "scope": "global"}
        if method == "getUsageStatistics":
            return self.usage.query(args)
        if method == "getWebSettings":
            return self.web.status()
        if method == "saveWebSettings":
            return self.web.save(args)
        if method == "testWebTools":
            return self.web.test()
        if method == "saveUserContextEntry":
            return self.user_context.save(args["entry"])
        if method == "removeUserContextEntry":
            return self.user_context.remove(args["id"])
        if method == "lanGetStatus":
            return self.lan.status()
        if method == "lanSetEnabled":
            return self.lan.set_enabled(args["enabled"])
        if method == "lanSetRemoteControl":
            return self.lan.set_remote_control(args["enabled"])
        if method == "remoteGetStatus":
            return self.remote_channels.status()
        if method == "remoteBeginLogin":
            return self.remote_channels.begin_login(args)
        if method == "remoteSubmitPin":
            return self.remote_channels.submit_pin(args["pin"])
        if method == "remoteStart":
            return self.remote_channels.start(args)
        if method == "remoteStop":
            return self.remote_channels.stop(args["channel"])
        if method == "remoteSwitchSession":
            return self.remote_channels.switch_session(args)
        if method == "remoteLogout":
            return self.remote_channels.logout(args["channel"])
        if method == "createSession":
            value = self.store.create_session(args["options"])
            value["permissionPolicy"] = self.store.get("settings", "behavior", {}).get("permissionPolicy", "confirm")
            self.save_session(value)
            self.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            return value["meta"]
        if method in {"listSessions", "listAllSessions"}:
            return [value for value in self.metas() if not args.get("cwd") or value["cwd"] == args["cwd"]]
        if method == "querySessionCatalog":
            query = args.get("query", args)
            rows = [
                meta
                for meta in self.metas()
                if (not query.get("cwd") or meta["cwd"] == query["cwd"])
                and bool(meta.get("archivedAt")) == bool(query.get("archived", False))
                and query.get("search", "").lower() in meta.get("name", "").lower()
            ]
            sort = query.get("sort", "modified")
            field = {"created": "createdAt", "archived": "archivedAt", "modified": "modifiedAt"}.get(sort, "modifiedAt")
            rows.sort(
                key=lambda row: row.get("name", "").casefold() if sort == "name" else row.get(field, row["createdAt"]),
                reverse=sort != "name",
            )
            offset = int(query.get("cursor") or 0)
            limit = min(max(int(query.get("limit") or 100), 1), 500)
            return {
                "sessions": rows[offset : offset + limit],
                "total": len(rows),
                "complete": True,
                "errors": 0,
                "revision": str(max((row.get("modifiedAt", 0) for row in rows), default=0)),
                **({"nextCursor": str(offset + limit)} if len(rows) > offset + limit else {}),
            }
        if method == "querySessionProjects":
            projects = {}
            for meta in self.metas():
                row = projects.setdefault(
                    meta["cwd"], {"cwd": meta["cwd"], "sessionCount": 0, "archivedCount": 0, "lastActive": 0}
                )
                row["sessionCount"] += 1
                row["archivedCount"] += bool(meta.get("archivedAt"))
                row["lastActive"] = max(row["lastActive"], meta.get("modifiedAt", meta["createdAt"]))
            return {"projects": list(projects.values()), "complete": True, "errors": 0, "revision": uuid4().hex}
        if method == "verifySessionCatalog":
            result = []
            for ref in args["references"]:
                meta = next(
                    (
                        meta
                        for meta in self.metas()
                        if meta["sessionId"] == ref.get("sessionId") or meta["sessionFile"] == ref.get("sessionFile")
                    ),
                    None,
                )
                result.append(
                    {
                        "reference": ref,
                        "status": "archived" if meta and meta.get("archivedAt") else "present" if meta else "missing",
                        **({"meta": meta} if meta else {}),
                    }
                )
            return result
        if method == "openSession":
            meta = next((meta for meta in self.metas() if meta["sessionFile"] == args["filePath"]), None)
            if not meta:
                child = next(
                    (
                        row
                        for row in self.store.list("delegated-session")
                        if row["meta"]["sessionFile"] == args["filePath"]
                    ),
                    None,
                )
                if child:
                    return child["meta"]
            if not meta:
                raise ValueError("Session file is not in the VERA desktop catalog.")
            value = self.sessions.get(meta["sessionId"])
            value["meta"]["active"] = True
            self.save_session(value)
            return value["meta"]
        if method == "closeSession":
            if key in self.sessions.running:
                return {"closed": False}
            value = self.store.get("session", key) or self.store.get("delegated-session", key)
            if value is None:
                return {"closed": True}  # Deletion may finish before a pending view-close acknowledgement.
            if value["meta"].get("parentSessionId"):
                return {"closed": True}  # The parent owns child updates; closing only unloads the inspection view.
            value["meta"]["active"] = False
            self.save_session(value)
            return {"closed": True}
        if method == "deleteSession":
            value = self.idle_session(key)
            (self.store.directory / "sessions" / (value["meta"]["sessionId"] + ".json")).unlink(missing_ok=True)
            self.store.delete("session", key)
            self.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            return None
        if method in {"archiveSession", "unarchiveSession"}:
            value = self.idle_session(key)
            if args["sessionFile"] != value["meta"]["sessionFile"] or args["expectedRevision"] != value["meta"].get(
                "archiveRevision", 0
            ):
                raise ValueError("Session archive revision changed. Refresh and retry.")
            value["meta"]["archiveRevision"] = args["expectedRevision"] + 1
            if method == "archiveSession":
                value["meta"]["archivedAt"] = int(time.time() * 1000)
            else:
                value["meta"].pop("archivedAt", None)
            self.save_session(value)
            self.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            return {
                "sessionId": key,
                "sessionFile": value["meta"]["sessionFile"],
                "archived": method == "archiveSession",
                "revision": value["meta"]["archiveRevision"],
                "archivedAt": value["meta"].get("archivedAt"),
            }
        if method == "prompt":
            return self.sessions.prompt(key, args["text"], args.get("document"), args.get("images"))
        if method == "abort":
            return self.sessions.abort(key)
        if method == "respondPermission":
            return self.sessions.respond(args)
        if method == "getPendingInteractions":
            return {
                "revision": self.events.sequence,
                "permissions": list(self.sessions.approvals.values()),
                "trust": [],
                "dialogs": [],
            }
        if method == "getSessionBaseline":
            return self.sessions.baseline(key)
        if method == "getSessionSelections":
            value = self.sessions.get(key)
            return {"selections": value["selections"], "permissionPolicy": value.get("permissionPolicy", "confirm")}
        if method == "getSessionMessages":
            return [
                {
                    **row,
                    "role": row["kind"],
                    "images": row.get("images", []),
                    "tools": [tool | {"isError": tool["state"] == "error"} for tool in row.get("tools", [])],
                }
                for row in self.sessions.get(key)["messages"]
            ]
        if method == "getSessionHistoryPage":
            raise ValueError("This session already returns its complete local history.")
        if method == "getLoadedSessions":
            return [
                {
                    "meta": meta,
                    "sequence": self.sessions.get(meta["sessionId"])["sequence"],
                    "permissionMode": self.sessions.get(meta["sessionId"])["permissionMode"],
                    "followUpQueue": [],
                    "streaming": meta["sessionId"] in self.sessions.running,
                    "compacting": False,
                }
                for meta in self.metas()
                if meta["active"]
            ]
        if method == "setModel":
            value = self.idle_session(key)
            model = {"provider": args["provider"], "modelId": args["modelId"]}
            self.providers.model_config(model)
            value["meta"]["model"] = model
            self.save_session(value)
            return None
        if method in {"setThinkingLevel", "setPermissionMode", "setSessionName", "setSessionSelections"}:
            value = self.idle_session(key)
            if method == "setThinkingLevel":
                value["meta"]["thinkingLevel"] = args["level"]
            elif method == "setPermissionMode":
                value["permissionMode"] = args["mode"]
                value["permissionPolicy"] = "yolo" if args["mode"] == "fullAccess" else "confirm"
            elif method == "setSessionSelections":
                if args.get("permissionPolicy") not in {None, "confirm", "yolo", "human"}:
                    raise ValueError("Invalid permission policy.")
                value["selections"].update(args.get("selections", {}))
                if args.get("permissionPolicy"):
                    value["permissionPolicy"] = args["permissionPolicy"]
                if options := args.get("modelOptions"):
                    for field, maximum in (("temperature", 2), ("topP", 1), ("topK", 100), ("toolCallLimit", 100000)):
                        if options.get(field):
                            number = float(options[field])
                            if not 0 <= number <= maximum or (
                                field in {"topK", "toolCallLimit"} and (not number.is_integer() or number < 1)
                            ):
                                raise ValueError("Invalid model option: " + field)
                    if options.get("reasoningParameter", "reasoning_effort") not in {
                        "reasoning_effort",
                        "reasoning.effort",
                    }:
                        raise ValueError("This runtime supports reasoning_effort or reasoning.effort.")
                    value["modelOptions"] = options
            else:
                value["meta"]["name"] = args["name"][:200]
            self.save_session(value)
            if method == "setSessionName":
                self.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            return None
        if method == "getPermissionMode":
            return self.sessions.get(key)["permissionMode"]
        if method == "getPermissionConfig":
            return {"enabled": True}
        if method == "getStats":
            return self.sessions.get(key)["stats"]
        if method == "getContextUsage":
            return None
        if method == "getFollowUpMessages":
            return [row["text"] for row in self.sessions.get(key).get("queue", [])]
        if method == "getTodos":
            return []
        if method == "clearQueue":
            value = self.sessions.get(key)
            value["queue"] = []
            self.save_session(value)
            self.sessions.emit(key, {"type": "queue_update", "steering": [], "followUp": []})
            return {"steering": [], "followUp": []}
        if method in {"markSessionHistoryReady", "setViewedSubagent"}:
            return None
        if method == "getSessionNavigation":
            return {
                "entries": [
                    {
                        "entryId": message["entryId"],
                        "ordinal": index,
                        "excerpt": message["text"][:120],
                        "timestamp": message["timestamp"],
                        "images": len(message["images"]),
                    }
                    for index, message in enumerate(self.sessions.get(key)["messages"])
                    if message["kind"] == "user"
                ]
            }
        if method in {"forkSession", "recallMessage"}:
            value = self.idle_session(key)
            ref = args["ref"]
            index = next(
                (
                    i
                    for i, row in enumerate(value["messages"])
                    if row["kind"] in ({"user"} if method == "recallMessage" else {"user", "assistant"})
                    and (row.get("entryId") == ref["entryId"] if "entryId" in ref else row["text"] == ref.get("text"))
                ),
                None,
            )
            if index is None:
                raise ValueError("Message no longer exists.")
            if method == "recallMessage":
                # Receipts remain immutable; removing UI history does not undo file operations.
                recalled = value["messages"][index]
                value["messages"] = value["messages"][:index]
                value["runtimeMessages"] = value["runtimeMessages"][: recalled.get("runtimeIndex", 0)]
                self.save_session(value)
                return {
                    "text": recalled["text"],
                    "images": recalled.get("images", []),
                    "document": recalled.get("document"),
                }
            target = value["messages"][index]
            include_target = int(target["kind"] == "assistant")
            runtime_index = target.get("runtimeIndex")
            if not include_target and runtime_index is None:
                runtime_index = 0
            if runtime_index is None:
                from vera.models.utils.content_string import get_content_string

                matches = [
                    i
                    for i, row in enumerate(value["runtimeMessages"])
                    if row.get("role") == "assistant" and get_content_string(row) == target["text"]
                ]
                occurrence = sum(
                    row.get("kind") == "assistant" and row.get("text") == target["text"]
                    for row in value["messages"][: index + 1]
                )
                if occurrence > len(matches):
                    raise ValueError("无法定位此历史回复的上下文，请选择另一条回复。")
                runtime_index = matches[occurrence - 1]
            child = self.store.create_session({"cwd": value["meta"]["cwd"], **(value["meta"].get("model") or {})})
            child["messages"] = deepcopy(value["messages"][: index + include_target])
            child["runtimeMessages"] = deepcopy(value["runtimeMessages"][: runtime_index + include_target])
            child["meta"].update(
                name=value["meta"].get("name", "") + " · 分叉",
                thinkingLevel=value["meta"].get("thinkingLevel", "default"),
            )
            child["permissionPolicy"] = value.get("permissionPolicy", "confirm")
            child["selections"] = deepcopy(value["selections"])
            self.save_session(child)
            self.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            return child["meta"]
        if method == "exportSession":
            rows = self.sessions.get(key)["messages"]
            if args["format"] == "jsonl":
                return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
            return "<!doctype html><meta charset='utf-8'><title>VERA session</title>" + "".join(
                f"<h2>{html.escape(row['kind'])}</h2><pre>{html.escape(row['text'])}</pre>" for row in rows
            )
        if method == "listProjectFiles":
            return ProjectFiles(Path(args["cwd"])).list()
        if method == "ensureProjectTrust":
            return Path(args["cwd"]).expanduser().resolve(strict=True).is_dir()
        if method in {"getGitBranch", "listGitBranches", "checkoutBranch"}:
            workspace = str(Path(args["cwd"]).resolve(strict=True))
            if method == "checkoutBranch":
                branch = args["branch"]
                if not branch or branch.startswith("-"):
                    raise ValueError("Invalid branch.")
                subprocess.run(["git", "-C", workspace, "switch", "--", branch], check=True, capture_output=True)
                return None
            result = subprocess.run(
                ["git", "-C", workspace, "branch", "--show-current"], capture_output=True, text=True
            )
            current = result.stdout.strip() or None
            if method == "getGitBranch":
                return current
            branches = subprocess.run(
                ["git", "-C", workspace, "branch", "--format=%(refname:short)"], capture_output=True, text=True
            )
            return {"current": current, "branches": branches.stdout.splitlines()}
        if method == "getChannelSubscriptionSessionIds":
            return []
        if method == "getChannelSubscriptions":
            # Desktop sessions have no topic subscriptions; preserve the shared snapshot contract.
            return {"sessionId": key, "topics": [], "generation": 0, "revision": 0, "live": False}
        if method in {"getChannelWatchConfig", "getCodemodeConfig"}:
            return {"enabled": False, "only": False}
        if method == "getCacheWarming":
            return {"mode": "off", "sessions": []}
        raise ValueError(f"{method} is not supported by this VERA runtime. No change was applied.")

    def close(self):
        self.remote_channels.close()
        self.taskboard_execution.close()
        self.taskboard.close()
        self.lan.close()
        self.sessions.close()
