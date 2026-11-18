"""Prompt-toolkit adapter for project @file and session /command selection."""

from contextlib import contextmanager

from prompt_toolkit.completion import Completer, Completion

from minisweagent.exceptions import InterruptAgentFlow
from minisweagent.terminal.files import MENTION
from minisweagent.terminal.session import COMMANDS, TerminalSession
from minisweagent.tools import ToolError


class TerminalCompleter(Completer):
    """Complete files and safe catalog metadata; completion performs no external service calls."""

    def __init__(self, session: TerminalSession):
        self.session = session

    def get_completions(self, document, complete_event):
        before = document.text_before_cursor
        if before.startswith("/") and "\n" not in before:
            command, separator, argument = before.partition(" ")
            if not separator:
                for name, description in COMMANDS.items():
                    if name == "/sandbox" and not self.session.catalog(name):
                        continue
                    if name.startswith(command):
                        yield Completion(name + " ", start_position=-len(before), display_meta=description)
                return
            try:
                rows = self.session.catalog(command)
            except (ToolError, ValueError, OSError):
                return
            if command in {"/skill", "/mcp", "/plugin"}:
                rows += [{"name": name, "description": "Session selection"} for name in ("all", "none")]
            elif command == "/subagent":
                rows += [{"name": "none", "description": "Clear selected role"}]
            elif command == "/sandbox" and (rows or self.session.sandbox_name):
                rows += [{"name": "none", "description": "Use the local host explicitly"}]
            if command != "/subagent" or not argument.strip() or " " not in argument.strip():
                query = argument.rsplit(",", 1)[-1].lstrip()
                for row in rows:
                    if query.casefold() in row["name"].casefold():
                        yield Completion(row["name"], start_position=-len(query), display_meta=row["description"])
                return
        matches = list(MENTION.finditer(before))
        marker = matches[-1] if matches and matches[-1].end() == len(before) else None
        if marker:
            query, length = marker[1] or marker[2], len(marker[0])
        elif before.endswith("@") and (len(before) == 1 or before[-2].isspace()):
            query, length = "", 1
        elif '@"' in before and before.rsplit('@"', 1)[1].find('"') == -1:
            query = before.rsplit('@"', 1)[1]
            length = len(query) + 2
        else:
            return
        for name in self.session.files.list(query):
            quoted = '@"' + name + '"' if any(char.isspace() for char in name) else "@" + name
            yield Completion(quoted, start_position=-length, display=name, display_meta="Project file context")


@contextmanager
def completion_context(session: TerminalSession):
    """Temporarily configure both existing prompts; restore state on failure or exit."""
    from minisweagent.agents.utils.prompt_user import _multiline_prompt_session, prompt_session

    saved = [
        (prompt, prompt.completer, prompt.complete_while_typing)
        for prompt in (prompt_session, _multiline_prompt_session)
    ]
    try:
        for prompt, _, _ in saved:
            prompt.completer = TerminalCompleter(session)
            prompt.complete_while_typing = True
        yield
    finally:
        for prompt, completer, complete_while_typing in saved:
            prompt.completer = completer
            prompt.complete_while_typing = complete_while_typing


def read_task(session, read, show) -> str | None:
    """Read commands until a task is ready; EOF or /stop at idle exits cleanly."""
    while True:
        try:
            text = read()
        except (EOFError, KeyboardInterrupt):
            return None
        try:
            result = session.process(text)
        except (ToolError, ValueError, OSError) as error:
            show(str(error))
            continue
        if result.kind == "stop":
            return None
        if result.kind == "task" and result.task.strip():
            return result.task
        show(result.message)


def bind_session(agent, session, show):
    """Handle user-only control at existing prompt boundaries, never in model/tool output."""

    def handle(text):
        if text.startswith("/") and not text.startswith("//"):
            try:
                result = session.process(text)
            except (ToolError, ValueError, OSError) as error:
                show(str(error))
                return None
            if result.kind in {"stop", "new"}:
                raise InterruptAgentFlow(
                    {
                        "role": "exit",
                        "content": result.message,
                        "extra": {
                            "exit_status": "Cancelled",
                            "terminal_action": result.kind,
                            "submission": "",
                        },
                    }
                )
            if result.kind == "task":
                return result.task
            show(result.message)
            return None
        if getattr(agent.config, "mode", "") == "human" or not text.strip():
            return text
        try:
            return session.files.attach(text[1:] if text.startswith("//") else text)
        except (ToolError, OSError) as error:
            show(str(error))
            return None

    agent.input_handler = handle
