"""Translate real runtime messages into the desktop's display-only event contract."""

import json
import time
from collections import deque
from threading import Condition
from uuid import uuid4

from vera.desktop.usage import token_usage


class EventBus:
    """Bounded replay buffer; a slow consumer must rehydrate after a cursor gap."""

    def __init__(self):
        self.condition = Condition()
        self.sequence = 0
        self.items = deque(maxlen=4096)

    def emit(self, method: str, payload) -> None:
        with self.condition:
            self.sequence += 1
            self.items.append({"cursor": self.sequence, "method": method, "payload": payload})
            self.condition.notify_all()

    def read(self, cursor: int, timeout: float = 20) -> dict:
        with self.condition:
            if cursor > self.sequence:
                return {"cursor": self.sequence, "reset": True, "events": []}
            if self.sequence <= cursor:
                self.condition.wait(timeout)
            if self.items and cursor < self.items[0]["cursor"] - 1:
                return {"cursor": self.sequence, "reset": True, "events": []}
            return {"cursor": self.sequence, "events": [item for item in self.items if item["cursor"] > cursor]}


def assistant_message(message: dict, model: dict | None) -> dict:
    """Project provider-independent text/actions; do not invent token usage."""
    raw = message.get("content", "")
    text = (
        raw
        if isinstance(raw, str)
        else "".join(part.get("text", "") for part in (raw or []) if part.get("type") in {"text", "output_text"})
    )
    for item in message.get("output", []):
        if item.get("type") == "message":
            text += "".join(
                part.get("text", "") for part in item.get("content", []) if part.get("type") == "output_text"
            )
    content = [{"type": "text", "text": text}]
    if reasoning := message.get("reasoning_content"):
        content.insert(0, {"type": "thinking", "thinking": reasoning})
    for item in message.get("output", []):
        if item.get("type") == "reasoning":
            for summary in item.get("summary", []):
                if summary.get("text"):
                    content.insert(0, {"type": "thinking", "thinking": summary["text"]})
    for action in message.get("extra", {}).get("actions", []):
        content.append(
            {
                "type": "toolCall",
                "id": action.get("tool_call_id") or uuid4().hex,
                "name": action.get("tool", "bash"),
                "arguments": action.get("arguments", {"command": action.get("command", "")}),
            }
        )
    response = message.get("extra", {}).get("response", message)
    response = response if isinstance(response, dict) else {}
    usage = response.get("usage") or {}
    counts = token_usage(usage)
    return {
        "role": "assistant",
        "content": content,
        "timestamp": int(time.time() * 1000),
        "api": "vera",
        "provider": (model or {}).get("provider", ""),
        "model": (model or {}).get("modelId", ""),
        "usage": {
            **counts,
            "cost": {
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "total": message.get("extra", {}).get("cost", 0),
            },
        },
        "usageReported": bool(usage),
        "stopReason": "toolUse" if len(content) > 1 else "stop",
    }


def message_events(message: dict):
    """Deliver complete response blocks through the existing display update contract.

    Updates represent complete blocks received from the runtime, not token streaming.
    The controller emits turn_end after the associated tools have finished.
    """
    yield {"type": "turn_start"}
    yield {"type": "message_start", "message": message}
    for index, part in enumerate(message["content"]):
        common = {"contentIndex": index, "partial": message}
        if part["type"] in {"text", "thinking"}:
            kind = part["type"]
            updates = [{"type": kind + "_delta", "delta": part.get(kind, ""), **common}]
        else:
            updates = [
                {"type": "toolcall_start", **common},
                {"type": "toolcall_end", "toolCall": part, **common},
            ]
        for update in updates:
            yield {"type": "message_update", "message": message, "assistantMessageEvent": update}
    yield {"type": "message_end", "message": message}


def history_message(message: dict) -> dict:
    """Convert a stream message to durable frontend history without provider secrets."""
    text = message.get("content", "")
    parts = text if isinstance(text, list) else [{"type": "text", "text": str(text)}]
    return {
        "id": uuid4().hex,
        "entryId": uuid4().hex,
        "kind": message["role"],
        "text": "".join(part.get("text", "") for part in parts if part.get("type") == "text"),
        "thinking": "".join(part.get("thinking", "") for part in parts if part.get("type") == "thinking"),
        "tools": [
            {
                "key": part["id"],
                "id": part["id"],
                "name": part["name"],
                "args": json.dumps(part["arguments"]),
                "output": "",
                "state": "running",
            }
            for part in parts
            if part.get("type") == "toolCall"
        ],
        "images": [],
        "timestamp": message["timestamp"],
    }


def transcript(session: dict, running: bool) -> dict:
    """Provide the full baseline required by the renderer's event boundary."""
    return {
        "messages": session["messages"],
        "streaming": session.get("liveStreaming") if running else None,
        "phase": "streaming" if running else "idle",
        "agentActive": running,
        "unseenCompletion": False,
        "followUpQueue": [row["text"] for row in session.get("queue", [])],
        "compacting": False,
        "todos": [],
        "pendingLlmError": None,
        "retrying": None,
        "compactionPause": None,
        "summarizationRetry": None,
    }


class LiveReply:
    """Mirror the renderer's live reply so reconnect/abort preserves received content."""

    def __init__(self, model):
        self.message = assistant_message({"content": ""}, model)
        self.state = {
            "id": uuid4().hex,
            "text": "",
            "thinking": "",
            "tools": [],
            "pendingImages": [],
            "subagentRuns": [],
            "subagentByToolCallId": {},
            "activeToolIndex": -1,
            "toolByContentIndex": {},
            "rawToolOutputs": {},
            "activity": [],
            "textBlockIndex": None,
        }

    def apply(self, frame):
        update = frame["update"]
        index, kind = update["contentIndex"], update["type"]
        if kind in {"text_delta", "thinking_delta"}:
            field = "text" if kind == "text_delta" else "thinking"
            self.state[field] += update["delta"]
            if field == "text" and self.state["textBlockIndex"] is None:
                self.state["textBlockIndex"] = index
        elif kind == "toolcall_start":
            call = frame["call"]
            self.state["toolByContentIndex"][str(index)] = len(self.state["tools"])
            self.state["tools"].append(
                {
                    "key": uuid4().hex,
                    "id": call["id"],
                    "name": call["name"],
                    "args": "",
                    "output": "",
                    "state": "running",
                    "blockIndex": index,
                }
            )
        else:
            tool = self.state["tools"][self.state["toolByContentIndex"][str(index)]]
            if kind == "toolcall_delta":
                tool["args"] += update["delta"]
            elif kind == "toolcall_end":
                call = update["toolCall"]
                tool.update(id=call["id"], name=call["name"], args=json.dumps(call["arguments"]))
        parts = []
        for tool in self.state["tools"]:
            while len(parts) <= tool["blockIndex"]:
                parts.append({"type": "text", "text": ""})
            parts[tool["blockIndex"]] = {"type": "toolCall", "id": tool["id"], "name": tool["name"], "arguments": {}}
        partial = self.message | {"content": parts}
        return {"type": "message_update", "message": partial, "assistantMessageEvent": update | {"partial": partial}}

    def history(self):
        """Retain partial text if stopped; unexecuted tool arguments stay display-only."""
        tools = [tool | {"state": "error"} for tool in self.state["tools"]]
        return {
            "id": self.state["id"],
            "entryId": self.state["id"],
            "kind": "assistant",
            "text": self.state["text"],
            "thinking": self.state["thinking"],
            "tools": tools,
            "timestamp": self.message["timestamp"],
        }
