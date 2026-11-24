"""Read-only child conversations projected from real delegated streams and receipts."""

import json
import time
from pathlib import Path
from uuid import uuid4

from vera.desktop.events import LiveReply, assistant_message, history_message


class DelegatedConversations:
    """Keep child inspection separate from executable chats and arbitrary file imports."""

    def __init__(self, sessions):
        self.sessions = sessions
        self.live = {}

    def start(self, parent_id, parent, frame):
        call_id = frame["toolCallId"]
        args = frame["args"]
        key = uuid4().hex
        now = int(time.time() * 1000)
        roles = self.sessions.store.get("settings", "roleModels", {})
        model = roles.get(args["role"]) or parent["meta"].get("model")
        child = {
            "meta": {
                "sessionId": key,
                "sessionFile": f"vera-subagent:{key}",
                "parentSessionId": parent_id,
                "cwd": parent["meta"]["cwd"],
                "name": args["role"],
                "model": model,
                "thinkingLevel": "default",
                "active": False,
                "readOnly": True,
                "createdAt": now,
                "modifiedAt": now,
                "messageCount": 1,
            },
            "messages": [
                {
                    "kind": "user",
                    "id": uuid4().hex,
                    "text": args["task"],
                    "thinking": "",
                    "tools": [],
                    "images": [],
                    "timestamp": now,
                }
            ],
            "sequence": 0,
            "permissionMode": parent["permissionMode"],
            "delegatedActive": True,
            "selections": {},
            "stats": {},
        }
        self.sessions.store.save("delegated-session", key, child)
        parent.setdefault("delegatedRuns", {})[call_id] = key
        self.sessions.store.save("session", parent_id, parent)
        return self.details(child, args["task"], "running")

    def details(self, child, task, status):
        """Use the renderer's existing Subagent result contract for clickable inspection."""
        return {
            "results": [
                {
                    "agent": child["meta"]["name"],
                    "task": task,
                    "status": status,
                    "sessionFile": child["meta"]["sessionFile"],
                    "exitCode": 0 if status == "done" else -1,
                }
            ]
        }

    def stream(self, parent, frame):
        call_id = frame["parentToolCallId"]
        key = parent.get("delegatedRuns", {}).get(call_id)
        if not key:
            return
        child = self.sessions.get(key)
        if frame["type"] == "stream_start":
            previous = self.live.pop(key, None)
            if previous:
                child["messages"].append(previous.history())
            self.live[key] = LiveReply(child["meta"].get("model"))
            event = {"type": "agent_start"}
        else:
            live = self.live.get(key)
            if live is None:
                return
            event = live.apply(frame)
        child["liveStreaming"] = self.live[key].state
        self.sessions.store.save("delegated-session", key, child)
        self.sessions.emit(key, event)

    def finish(self, parent, frame):
        """Import only a host-owned trajectory under this desktop's artifacts directory."""
        key = parent.get("delegatedRuns", {}).get(frame["toolCallId"])
        if not key:
            return None
        child = self.sessions.get(key)
        try:
            result = json.loads(frame["result"].get("output", "{}"))
        except (ValueError, TypeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        trajectory = result.get("trajectory")
        messages = []
        if trajectory:
            path = Path(trajectory).resolve()
            root = (self.sessions.store.directory / "artifacts").resolve()
            if path.is_relative_to(root) and path.is_file():
                try:
                    stored = json.loads(path.read_text(encoding="utf-8"))
                    imported = stored.get("messages", []) if isinstance(stored, dict) else []
                    if isinstance(imported, list) and all(isinstance(item, dict) for item in imported):
                        messages = imported
                except (OSError, ValueError):
                    # A partial trajectory must not prevent settling the live child.
                    pass
        if messages:
            child["messages"] = child["messages"][:1]
            for raw in messages:
                if raw.get("role") == "assistant":
                    message = assistant_message(raw, child["meta"].get("model"))
                    child["messages"].append(history_message(message))
                    if self.sessions.usage:
                        identity = raw.get("extra", {}).get("usage_id") or uuid4().hex
                        self.sessions.usage.record(identity, message, child["meta"]["cwd"])
                elif raw.get("role") == "tool":
                    for message in reversed(child["messages"]):
                        tool = next(
                            (item for item in message.get("tools", []) if item["id"] == raw.get("tool_call_id")), None
                        )
                        if tool:
                            tool.update(output=raw.get("content", ""), state="done")
                            break
        elif live := self.live.get(key):
            child["messages"].append(live.history())
        if result.get("summary"):
            child["messages"].append(
                history_message(
                    assistant_message({"role": "assistant", "content": result["summary"]}, child["meta"].get("model"))
                )
            )
        self.live.pop(key, None)
        child.pop("liveStreaming", None)
        child["delegatedActive"] = False
        child["meta"]["messageCount"] = len(child["messages"])
        self.sessions.store.save("delegated-session", key, child)
        self.sessions.emit(key, {"type": "agent_settled", "aborted": result.get("status") != "Submitted"})
        return self.details(
            child, child["messages"][0]["text"], "done" if result.get("status") == "Submitted" else "failed"
        )
