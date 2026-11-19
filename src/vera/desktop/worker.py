"""One isolated desktop run using the unchanged runtime loop and JSON-line input."""

import json
import sys
from pathlib import Path
from uuid import uuid4

from vera.agents.hindsight import HindsightInteractiveAgent
from vera.agents.stateful import StatefulInteractiveAgent
from vera.desktop.protocol import send
from vera.exceptions import LimitsExceeded, Submitted, UserInterruption
from vera.models.utils.content_string import get_content_string


class DesktopAgent(StatefulInteractiveAgent):
    """Adapt message observation and input outside the inherited Agent Loop.

    A fresh process receives the previous conversation, which is inserted when
    the base loop initializes the next task. All tool dispatch still goes through
    the runtime registry and RunStore receipts. Confirmation waits for a scoped
    desktop reply on stdin; absent input denies execution.
    """

    def __init__(self, *args, **kwargs):
        workspace = kwargs.pop("desktop_workspace", None)
        self.tool_call_limit = kwargs.pop("desktop_tool_call_limit", 500)
        self.tool_calls = 0
        super().__init__(*args, **kwargs)
        if workspace and callable(getattr(self.model, "bind_tool_registry", None)):
            from vera.desktop.project_tools import register_project_tools
            from vera.tools import make_tool_registry

            if self.tool_registry is None:
                self.tool_registry = make_tool_registry(self.env)
                self.model.bind_tool_registry(self.tool_registry)
            register_project_tools(self.tool_registry, Path(workspace))
        self.prior_messages = []
        self.human_dispatched = False

    def query(self):
        """Human mode runs exactly the submitted command without a model request."""
        if self.config.mode != "human":
            return super().query()
        if self.human_dispatched:
            raise Submitted(
                {
                    "role": "exit",
                    "content": "Human command completed.",
                    "extra": {"exit_status": "Submitted", "submission": "Human command completed."},
                }
            )
        self.human_dispatched = True
        message = {
            "role": "assistant",
            "content": "Run the user-entered command.",
            "extra": {"actions": [{"command": self.extra_template_vars["task"], "tool_call_id": uuid4().hex}]},
        }
        self.add_messages(message)
        return message

    def add_messages(self, *messages: dict) -> list[dict]:
        if not self.messages and self.prior_messages:
            self.messages.extend(self.prior_messages)
            self.prior_messages = []
            messages = tuple(message for message in messages if message.get("role") != "system")
        for message in messages:
            for action in message.get("extra", {}).get("actions", []):
                action.setdefault("tool_call_id", uuid4().hex)
            if message.get("role") == "assistant" or message.get("object") == "response":
                send("message", message=message)
            elif message.get("role") == "exit":
                content = get_content_string(message)
                if content and message.get("extra", {}).get("exit_status") == "Submitted":
                    send("message", message={"role": "assistant", "content": content, "extra": {}})
                elif message.get("extra", {}).get("exit_status"):
                    send("notice", text="Run stopped: " + str(message["extra"]["exit_status"]))
        return super().add_messages(*messages)

    def _ask_confirmation_or_interrupt(self, commands, *, tool_calls=()):
        if self.config.mode != "confirm":
            return
        actions = [{"tool": "bash", "arguments": {"command": command}} for command in commands]
        actions += list(tool_calls)
        for action in actions:
            if action.get("tool") == "bash" and not self._should_ask_confirmation(
                action.get("arguments", {}).get("command", "")
            ):
                continue
            request_id = uuid4().hex
            send("approval", requestId=request_id, action=action)
            reply = sys.stdin.readline()
            value = json.loads(reply) if reply else {}
            if value.get("requestId") != request_id or value.get("answer") not in {"allow", "allowAlways", "allowDir"}:
                raise UserInterruption({"role": "user", "content": "User denied this operation."})

    def _prompt_and_handle_slash_commands(self, *_args, **_kwargs):
        request_id = uuid4().hex
        send("human_input", requestId=request_id)
        value = json.loads(sys.stdin.readline() or "{}")
        if value.get("requestId") != request_id or not isinstance(value.get("text"), str):
            raise EOFError("Human command input cancelled.")
        return value["text"]

    def _execute_action(self, action: dict) -> dict:
        if self.tool_calls >= self.tool_call_limit:
            raise LimitsExceeded(
                {"role": "exit", "content": "Tool call limit reached.", "extra": {"exit_status": "LimitsExceeded"}}
            )
        self.tool_calls += 1
        call_id = action.setdefault("tool_call_id", uuid4().hex)
        name = action.get("tool", "bash")
        arguments = action.get("arguments", {"command": action.get("command", "")})
        send("tool_start", toolCallId=call_id, toolName=name, args=arguments)
        try:
            result = super()._execute_action(action)
        except BaseException:
            send("tool_end", toolCallId=call_id, toolName=name, result={"output": "Operation interrupted or finished."})
            raise
        send("tool_end", toolCallId=call_id, toolName=name, result=result)
        return result


class DesktopHindsightAgent(DesktopAgent, HindsightInteractiveAgent):
    """Keep Hindsight recall/context projection while adapting desktop input and events."""


def main() -> None:
    """Read a private stdin request; never put decrypted credentials in argv or a request file."""
    import contextlib

    from vera.runtime import open_agent_runtime
    from vera.storage import RunStore

    request = json.loads(sys.stdin.readline())
    config = request["config"]
    model = config.get("model", {})
    if model.get("model_class", "litellm") in {"litellm", "litellm_response"}:
        model["model_class"] = (
            "vera.desktop.streaming.StreamingResponsesModel"
            if model.get("model_class") == "litellm_response"
            else "vera.desktop.streaming.StreamingChatModel"
        )
    memory_agent = config.get("agent", {}).get("agent_class") in {"hindsight", "hindsight_interactive"} or any(
        key in config.get("agent", {}) for key in ("memory_bank_id", "memory_mode", "context_budget_chars")
    )
    config.setdefault("agent", {}).update(
        agent_class="vera.desktop.worker.DesktopHindsightAgent" if memory_agent else "vera.desktop.worker.DesktopAgent",
        confirm_exit=False,
        output_path=request["trajectory"],
    )

    def run_turn(task, history, remaining=None):
        from copy import deepcopy

        selected = deepcopy(config)
        if remaining:
            selected["agent"]["cost_limit"] = min(selected["agent"].get("cost_limit", 1), remaining["cost"])
            selected["agent"]["wall_time_limit_seconds"] = max(1, int(remaining["seconds"]))
        with open_agent_runtime(selected) as runtime:
            runtime.agent.prior_messages = history
            store = RunStore(Path(request["database"]))
            with store.track(runtime.agent, workspace=runtime.workspace, runtime_policy=runtime.policy):
                result = runtime.agent.run(task)
            send("finished", result=result, messages=runtime.agent.messages, cost=runtime.agent.cost)
            return runtime.agent

    with contextlib.redirect_stdout(sys.stderr):
        if config.get("run_mode") == "goal":
            from vera.modes.goals import drive_goal
            from vera.terminal.session import TerminalSession

            session = TerminalSession(config, Path(config["sandbox"]["workspace"]))
            session.run_mode = "goal"
            drive_goal(session, run_turn, lambda text: send("notice", text=text))
        else:
            run_turn(request["task"], request.get("history", []))


if __name__ == "__main__":
    main()
