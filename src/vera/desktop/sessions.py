"""Concurrent desktop conversations with isolated workers, receipts and approvals."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from vera.config import get_config_from_spec
from vera.desktop.events import LiveReply, assistant_message, history_message, message_events, transcript
from vera.desktop.model_settings import ModelOptions, apply_reasoning
from vera.desktop.performance import TaskObservation
from vera.evolution.process import _kill_tree
from vera.terminal.session import TerminalSession
from vera.utils.serialize import recursive_merge, strip_sensitive


class Sessions:
    """Own process lifetimes and ordered event persistence for independent chats."""

    def __init__(self, store, providers, events, config: dict | None = None):
        self.store, self.providers, self.events = store, providers, events
        self.lock = threading.RLock()
        self.running = {}
        self.approvals = {}
        self.cancelled = set()
        self.watchers = set()
        self.base_config = config
        self.user_context_directory = store.directory / "user-context"
        self.usage = None
        from vera.desktop.delegation import DelegatedConversations

        self.delegation = DelegatedConversations(self)

    def get(self, key: str) -> dict:
        value = self.store.get("session", key)
        if value is None:
            value = self.store.get("delegated-session", key)
        if value is None:
            raise ValueError("Unknown session.")
        return value

    def emit(self, key: str, event: dict) -> None:
        with self.lock:
            value = self.get(key)
            value["sequence"] += 1
            value["meta"]["modifiedAt"] = int(time.time() * 1000)
            kind = "delegated-session" if value["meta"].get("parentSessionId") else "session"
            self.store.save(kind, key, value)
            self.events.emit("onEvent", {"sessionId": key, "sequence": value["sequence"], "event": event})

    def baseline(self, key: str) -> dict:
        with self.lock:
            value = self.get(key)
            return {
                "hydrationToken": key,
                "meta": value["meta"],
                "sequence": value["sequence"],
                "transcript": transcript(value, key in self.running or value.get("delegatedActive", False)),
                "permissionMode": value["permissionMode"],
            }

    def config(self, value: dict) -> dict:
        from copy import deepcopy

        config = deepcopy(self.base_config) if self.base_config else get_config_from_spec("vera.yaml")
        if self.base_config is None:
            config = recursive_merge(config, get_config_from_spec("desktop/assistant.yaml"))
        behavior = self.store.get("settings", "behavior", {})
        from vera.desktop.shells import shell_command

        config.setdefault("environment", {})["shell_command"] = shell_command(behavior.get("commandShell", "system"))
        permission = value.get("permissionPolicy", behavior.get("permissionPolicy", "confirm"))
        if permission == "human":
            config["model"] = {
                "model_class": "deterministic",
                "model_name": "manual",
                "outputs": [],
                "cost_per_call": 0,
            }
        elif value["meta"].get("model"):
            templates = {
                name: config.get("model", {})[name]
                for name in ("format_error_template", "observation_template", "multimodal_regex", "allow_text_final")
                if name in config.get("model", {})
            }
            config["model"] = self.providers.model_config(value["meta"]["model"]) | templates
        elif not config.get("model", {}).get("model_name"):
            raise ValueError("Configure and select a model before sending a task.")
        if config["model"].get("model_class", "litellm") in {"litellm", "litellm_response"}:
            config["model"]["cost_tracking"] = "tokens"
            config["agent"]["cost_limit"] = 0
        config["agent"].update(mode=permission)
        config["agent"]["desktop_workspace"] = value["meta"]["cwd"]
        reference = value["meta"].get("model")
        definition = self.providers.definition(reference) if reference and permission != "human" else {}
        raw_options = definition.get("advanced")
        if raw_options is None:
            raw_options = {name: item for name, item in (value.get("modelOptions") or {}).items() if item != ""}
        options = ModelOptions.model_validate(raw_options).model_dump(by_alias=True)
        if options.get("toolCallLimit"):
            config["agent"]["desktop_tool_call_limit"] = int(options["toolCallLimit"])
        kwargs = config["model"].setdefault("model_kwargs", {})
        for field, parameter in (("temperature", "temperature"), ("topP", "top_p"), ("topK", "top_k")):
            if options.get(field) is not None:
                kwargs[parameter] = float(options[field]) if field != "topK" else int(options[field])
        level = value["meta"].get("thinkingLevel", "off")
        if reference and permission != "human":
            kwargs.update(self.providers.reasoning_kwargs(reference, level, options))
        elif level not in {"off", "default"}:
            parameter = options.get("reasoningParameter", "reasoning_effort")
            if definition.get("advanced") and level not in options["reasoningValues"]:
                raise ValueError("所选模型不支持此思考强度，请重新选择。")
            apply_reasoning(kwargs, parameter, level)
        config["sandbox"] = {"mode": "local", "workspace": value["meta"]["cwd"]}
        config["sandbox_profiles"] = {"path": str(self.store.directory / "sandboxes.sqlite3")}
        if sandbox := value["selections"].get("sandbox") or behavior.get("defaultSandbox"):
            config["sandbox_profile"] = sandbox
        config["terminal"] = {"session_id": value["meta"]["sessionId"]}
        # Parent and workers must share one explicit goal root despite different startup environments.
        config["goal"] = {
            "max_turns": 0,
            "cost_limit": 0,
            "timeout": 0,
            **config.get("goal", {}),
            "directory": str(self.store.directory / "goals"),
        }
        config["plugins"] = {"directory": str(self.store.directory / "plugins")}
        if "plugins" in value["selections"]:
            config["plugins"]["names"] = value["selections"]["plugins"]
        config["skills"] = {"directories": [str(self.store.directory / "skills")]}
        mcp = self.store.get("settings", "mcp", {})
        config["mcp_servers"] = {name: entry["config"] for name, entry in mcp.items() if entry["enabled"]}
        config["subagents"] = {"roles": self.store.get("settings", "roles", {})}
        config["desktop_subagent_refs"] = {}
        preferences = self.store.get("settings", "modelPrefs", {})
        for name, role in config["subagents"]["roles"].items():
            reference = self.store.get("settings", "roleModels", {}).get(name)
            if selected := preferences.get("subagentModels", {}).get(name):
                provider, _, model_id = selected.partition("/")
                reference = {"provider": provider, "modelId": model_id}
            if reference:
                role["model"] = self.providers.model_config(reference)
                config["desktop_subagent_refs"][name] = reference
        config["web"] = self.store.get("settings", "web", config.get("web", {}))
        config["user_context"] = {"directory": str(self.user_context_directory)}
        return config

    def terminal(self, value: dict, config: dict | None = None) -> TerminalSession:
        """Apply only validated session-local selections to the shared terminal adapter."""
        config = config or self.config(value)
        session = TerminalSession(config, Path(value["meta"]["cwd"]))
        session.skills = value["selections"].get("skills", [])
        session.mcp = value["selections"].get("mcp")
        session.run_mode = value["selections"].get("runMode", "normal")
        return session

    def prompt(self, key: str, text: str, document: dict | None = None, images: list | None = None) -> None:
        """Accept once, then publish real worker progress; failures never report success."""
        started, timestamp = time.monotonic(), int(time.time() * 1000)
        with self.lock:
            value = self.get(key)
            if value["meta"].get("parentSessionId"):
                raise ValueError("Subagent conversations are read-only. Continue in the parent conversation.")
            if value["meta"].get("archivedAt"):
                raise ValueError("Unarchive this session before running it.")
            if key in self.running:
                if key in self.cancelled:
                    raise ValueError("This task is stopping. Wait until it settles before sending another task.")
                if value.get("queue"):
                    raise ValueError("A follow-up is already queued.")
                if text.startswith("/"):
                    raise ValueError("Stop the current task before changing its mode or capabilities.")
                value["queue"] = [{"text": text, "document": document, "images": images}]
                self.store.save("session", key, value)
                self.emit(key, {"type": "queue_update", "steering": [], "followUp": [text]})
                return
            config = self.config(value)
            if images and value["meta"].get("model"):
                definition = self.providers.definition(value["meta"]["model"])
                if not definition.get("imageInput", False):
                    raise ValueError("当前模型未启用图片输入，请切换支持图片的模型后重试。")
            terminal = self.terminal(value, config)
            if document:
                text = ""
                for part in document["parts"]:
                    if part["type"] == "text":
                        text += part["text"]
                    elif part["type"] == "skill":
                        terminal.process("/skill " + part["id"])
                    elif part["type"] == "file":
                        path = Path(part["path"])
                        if path.is_absolute():
                            path = path.resolve().relative_to(Path(value["meta"]["cwd"]).resolve())
                        text += '@"' + path.as_posix() + '"'
                    else:
                        raise ValueError("Unknown composer part.")
            original = text
            if terminal.run_mode in {"plan", "goal"} and not text.startswith("/"):
                text = "/" + terminal.run_mode + " " + text
            result = terminal.process(text)
            if result.kind != "task":
                value["selections"] = {
                    "skills": terminal.skills,
                    "mcp": terminal.mcp,
                    "sandbox": terminal.sandbox_name,
                    "runMode": terminal.run_mode,
                    "plugins": terminal.config.get("plugins", {}).get("names"),
                }
                self.store.save("session", key, value)
                reply = assistant_message({"content": result.message}, None)
                value["messages"].append(history_message(reply))
                self.store.save("session", key, value)
                for event in message_events(reply):
                    self.emit(key, event)
                self.emit(key, {"type": "turn_end", "message": reply, "toolResults": []})
                self.emit(key, {"type": "agent_settled", "aborted": False})
                self.store.checkpoint_session(self.get(key))
                return
            config = terminal.runtime_config()
            if config["agent"].get("mode") == "human":
                # Manual Bash needs only its selected execution environment, never model-side services.
                config["mcp_servers"] = {}
                config["mcp_selection"] = []
                config["plugins"]["names"] = []
                config["web"] = {}
                config["subagents"]["roles"] = {}
            # Human commands do not use the selected provider or require its credentials.
            if config["agent"].get("mode") != "human" and (provider_ref := value["meta"].get("model")):
                config["desktop_provider_ref"] = provider_ref
                config["desktop_state_dir"] = str(self.store.directory)
                config = strip_sensitive(config)
            # Explicit --config credentials have no provider reference to restore.
            # They travel only through the worker's private stdin, never a request file.
            task = result.task
            if images:
                # The existing multimodal adapter expands these markers.
                for image in images:
                    if image["mimeType"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                        raise ValueError("Unsupported image type.")
                    task += (
                        "\n<VERA_MULTIMODAL_CONTENT><CONTENT_TYPE>image_url</CONTENT_TYPE>data:"
                        + image["mimeType"]
                        + ";base64,"
                        + image["data"]
                        + "</VERA_MULTIMODAL_CONTENT>"
                    )
            run = self.store.directory / "artifacts" / uuid4().hex
            run.mkdir(parents=True)
            request = {
                "config": config,
                "task": task,
                "history": value["runtimeMessages"],
                "trajectory": str(run / "trajectory.json"),
                "database": str(self.store.directory / "runs.sqlite3"),
            }
            request_path = run / "request.json"
            user = {"role": "user", "content": original, "timestamp": int(time.time() * 1000)}
            value["messages"].append(
                history_message(user)
                | {"runtimeIndex": len(value["runtimeMessages"])}
                | ({"document": document} if document else {})
                | ({"images": images} if images else {})
            )
            value["meta"]["messageCount"] = len(value["messages"])
            if not value["meta"].get("name"):
                value["meta"]["name"] = original[:70]
            self.store.save("session", key, value)
            environment = os.environ | {
                "VERA_SILENT_STARTUP": "1",
                "PYTHONUTF8": "1",
                "VERA_GLOBAL_CONFIG_DIR": str(self.store.directory),
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            }
            if config.get("web") and config.get("run_mode") != "plan":
                from vera.desktop.web import WebSettings

                environment.update(WebSettings(self.store).environment(config["web"]))
            error_log = (run / "worker.log").open("w", encoding="utf-8")
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "vera.desktop.worker", "-"],
                    cwd=value["meta"]["cwd"],
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=error_log,
                    text=True,
                    encoding="utf-8",
                    start_new_session=os.name != "nt",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            finally:
                error_log.close()
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            self.running[key] = process
            self.emit(key, {"type": "session_info_changed", "name": value["meta"].get("name")})
            self.emit(key, {"type": "agent_start"})
            self.emit(key, {"type": "message_start", "message": user})
            self.emit(key, {"type": "message_end", "message": user})
            self.events.emit("onSessionCatalogChanged", {"revision": uuid4().hex, "complete": True})
            observation = (
                TaskObservation(
                    self.usage, run.name, value["meta"].copy(), started, timestamp, bool(value["runtimeMessages"])
                )
                if self.usage
                else None
            )
            watcher = threading.Thread(target=self._watch, args=(key, process, request_path, observation), daemon=True)
            self.watchers.add(watcher)
            watcher.start()

    def _watch(self, key, process, request_path, observation=None):
        completed = False
        pending_message = None
        live = None
        try:
            for line in process.stdout:
                frame = json.loads(line)
                with self.lock:
                    value = self.get(key)
                    if observation:
                        observation.observe(frame)
                    if frame.get("parentToolCallId") and frame["type"] in {"stream_start", "stream_delta"}:
                        self.delegation.stream(value, frame)
                        continue
                    if frame["type"] == "tools_ready":
                        configured = self.store.get("settings", "mcp", {})
                        from vera.tools.mcp import mcp_tool_name

                        statuses = [
                            {
                                "name": name,
                                "tools": [
                                    {"name": tool}
                                    for tool in frame["names"]
                                    if tool.startswith(mcp_tool_name(name, ""))
                                ],
                            }
                            for name in configured
                        ]
                        self.events.emit("onMcpServersChanged", {"servers": statuses})
                    elif frame["type"] == "stream_start":
                        if pending_message:
                            self.emit(key, {"type": "turn_end", "message": pending_message, "toolResults": []})
                            pending_message = None
                        elif live:
                            # Preserve an interrupted attempt before a model retry starts.
                            value["messages"].append(live.history())
                            self.emit(key, {"type": "turn_end", "message": live.message, "toolResults": []})
                        live = LiveReply(value["meta"].get("model"))
                        value["liveStreaming"] = live.state
                        self.store.save("session", key, value)
                        self.emit(key, {"type": "turn_start"})
                        self.emit(key, {"type": "message_start", "message": live.message})
                    elif frame["type"] == "stream_delta" and live:
                        event = live.apply(frame)
                        value["liveStreaming"] = live.state
                        self.store.save("session", key, value)
                        self.emit(key, event)
                    elif frame["type"] == "message":
                        if pending_message:
                            self.emit(key, {"type": "turn_end", "message": pending_message, "toolResults": []})
                        message = assistant_message(frame["message"], value["meta"].get("model"))
                        if not message["model"] and self.base_config:
                            reference = self.base_config.get("model", {}).get("model_name", "configured/unknown")
                            message["provider"], _, message["model"] = reference.partition("/")
                        history = history_message(message)
                        if "runtimeIndex" in frame:
                            history["runtimeIndex"] = frame["runtimeIndex"]
                        if self.usage:
                            identifier = frame["message"].get("extra", {}).get("usage_id") or history["id"]
                            self.usage.record(identifier, message, value["meta"]["cwd"])
                        pending_message = message
                        value["messages"].append(history)
                        value["stats"]["inputTokens"] += message["usage"]["input"]
                        value["stats"]["outputTokens"] += message["usage"]["output"]
                        self.store.save("session", key, value)
                        if live:
                            self.emit(key, {"type": "message_end", "message": message})
                            live = None
                            value.pop("liveStreaming", None)
                            self.store.save("session", key, value)
                        else:
                            for event in message_events(message):
                                self.emit(key, event)
                    elif frame["type"] in {"tool_start", "tool_end"}:
                        self._tool(key, value, frame)
                    elif frame["type"] in {"approval", "human_input"}:
                        self._approval(key, frame)
                    elif frame["type"] == "notice":
                        self.events.emit(
                            "onExtensionNotify", {"level": "info", "message": frame["text"], "extensionPath": "VERA"}
                        )
                    elif frame["type"] == "usage" and self.usage:
                        self.usage.record(
                            frame["id"],
                            {
                                "provider": (value["meta"].get("model") or {}).get("provider", "configured"),
                                "model": (value["meta"].get("model") or {}).get("modelId", "unknown"),
                            }
                            | frame["message"],
                            value["meta"]["cwd"],
                        )
                    elif frame["type"] == "finished":
                        completed = True
                        value["lastRunResult"] = strip_sensitive(frame["result"])
                        value["runtimeMessages"] = [m for m in frame["messages"] if m.get("role") != "exit"]
                        value["stats"]["cost"] += frame["cost"]
                        value["meta"]["messageCount"] = len(value["messages"])
                        self.store.save("session", key, value)
            process.wait(timeout=10)
            if not completed and key not in self.cancelled:
                message = assistant_message(
                    {"content": "Task failed. Review the local run receipts and provider configuration."}, None
                )
                message.update(stopReason="error", errorMessage="Worker exited without a completion receipt.")
                value = self.get(key)
                value["messages"].append(
                    {
                        "kind": "system",
                        "id": uuid4().hex,
                        "text": message["errorMessage"],
                        "timestamp": message["timestamp"],
                    }
                )
                self.store.save("session", key, value)
                self.emit(key, {"type": "turn_end", "message": message, "toolResults": []})
        finally:
            request_path.unlink(missing_ok=True)  # Do not retain decrypted provider credentials.
            with self.lock:
                value = self.get(key)
                if key in self.cancelled or not completed:
                    value["lastRunResult"] = {
                        "exit_status": "Cancelled" if key in self.cancelled else "WorkerFailed",
                        "submission": "",
                    }
                if live:
                    value["messages"].append(live.history())
                value.pop("liveStreaming", None)
                self.store.save("session", key, value)
                if pending_message:
                    self.emit(key, {"type": "turn_end", "message": pending_message, "toolResults": []})
                self.store.checkpoint_session(self.get(key))
                if observation:
                    observation.finish(value["lastRunResult"].get("exit_status", "WorkerFailed"))
                self.running.pop(key, None)
                for call_id, child_id in value.get("delegatedRuns", {}).items():
                    if self.get(child_id).get("delegatedActive"):
                        self.delegation.finish(value, {"toolCallId": call_id, "result": {}})
                for request_id, pending in list(self.approvals.items()):
                    if pending["sessionId"] == key:
                        self.approvals.pop(request_id)
                        self.events.emit(
                            "onPermissionResolved", {"sessionId": key, "requestId": request_id, "answered": False}
                        )
                self.emit(key, {"type": "agent_end", "messages": [], "willRetry": False})
                self.emit(key, {"type": "agent_settled", "aborted": key in self.cancelled})
                queued = self.get(key).get("queue", []) if key not in self.cancelled else []
                if queued:
                    value = self.get(key)
                    value["queue"] = []
                    self.store.save("session", key, value)
                    self.emit(key, {"type": "queue_update", "steering": [], "followUp": []})
                    self.prompt(key, **queued[0])
                self.cancelled.discard(key)
                self.watchers.discard(threading.current_thread())

    def _tool(self, key, value, frame):
        event = {
            "type": "tool_execution_start" if frame["type"] == "tool_start" else "tool_execution_end",
            "toolCallId": frame["toolCallId"],
            "toolName": frame["toolName"],
        }
        if frame["type"] == "tool_start":
            event["args"] = frame["args"]
            if frame["toolName"] == "subagent_run":
                details = self.delegation.start(key, value, frame)
                value["messages"].append(
                    {
                        "kind": "subagent",
                        "id": uuid4().hex,
                        "timestamp": int(time.time() * 1000),
                        "runs": [{**run, "key": frame["toolCallId"]} for run in details["results"]],
                    }
                )
                for message in value["messages"]:
                    if "tools" in message:
                        message["tools"] = [tool for tool in message["tools"] if tool["id"] != frame["toolCallId"]]
                self.store.save("session", key, value)
                event.update(toolName="subagent", args={"agent": frame["args"]["role"], "task": frame["args"]["task"]})
                self.emit(key, event)
                self.emit(
                    key,
                    {
                        "type": "tool_execution_update",
                        "toolCallId": frame["toolCallId"],
                        "toolName": "subagent",
                        "partialResult": {"details": details},
                    },
                )
                return
        else:
            result = frame["result"]
            output = str(result.get("output", ""))
            event.update(
                result={"content": [{"type": "text", "text": output}]}, isError=bool(result.get("returncode", 0))
            )
            if frame["toolName"] == "subagent_run":
                if details := self.delegation.finish(value, frame):
                    event["result"]["details"] = details
                    # Reconnects and active inspection retain the same card throughout execution.
                    for message in value["messages"]:
                        if message.get("kind") == "subagent" and any(
                            run["key"] == frame["toolCallId"] for run in message["runs"]
                        ):
                            message["runs"] = [{**run, "key": frame["toolCallId"]} for run in details["results"]]
                    self.store.save("session", key, value)
            for message in reversed(value["messages"]):
                tool = next((tool for tool in message.get("tools", []) if tool["id"] == frame["toolCallId"]), None)
                if tool:
                    tool.update(output=output, state="error" if event["isError"] else "done")
                    if frame["toolName"] == "subagent_run":
                        message["tools"].remove(tool)
                    self.store.save("session", key, value)
                    break
        self.emit(key, event)

    def _approval(self, key, frame):
        request = {
            "id": frame["requestId"],
            "sessionId": key,
            "title": "Human command input" if frame["type"] == "human_input" else "Approve operation",
            "message": json.dumps(frame.get("action", {}), ensure_ascii=False),
            "kind": "command",
            "allowedAnswers": ["allow", "deny"],
        }
        self.approvals[request["id"]] = request
        self.events.emit("onPermissionRequest", request)

    def respond(self, value: dict):
        with self.lock:
            key = value["requestId"]
            request = self.approvals.get(key)
            if not request or (value.get("sessionId") and request["sessionId"] != value["sessionId"]):
                raise ValueError("Approval expired or belongs to another session.")
            if value.get("answer") not in request["allowedAnswers"]:
                raise ValueError("This request supports allow once or deny.")
            value = value | {"sessionId": request["sessionId"]}
            process = self.running.get(value["sessionId"])
            if not process or process.poll() is not None:
                raise ValueError("Run no longer active.")
            process.stdin.write(json.dumps(value) + "\n")
            process.stdin.flush()
            self.approvals.pop(key)
            self.events.emit(
                "onPermissionResolved", {"sessionId": value["sessionId"], "requestId": key, "answered": True}
            )

    def abort(self, key: str) -> None:
        """Clear owned queued work even if an exited worker still awaits watcher settlement."""
        with self.lock:
            process = self.running.get(key)
            if process:
                self.cancelled.add(key)
                value = self.get(key)
                value["queue"] = []
                self.store.save("session", key, value)
                self.emit(key, {"type": "queue_update", "steering": [], "followUp": []})
                if process.poll() is None:
                    _kill_tree(process.pid)

    def close(self):
        for key in list(self.running):
            self.abort(key)
        for watcher in list(self.watchers):
            watcher.join(timeout=10)
