"""Declarative session selection and slash commands, with no terminal or model IO."""

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from minisweagent.plugins import PluginManager, load_plugins
from minisweagent.plugins.runtime import PluginConfig
from minisweagent.terminal.files import ProjectFiles
from minisweagent.tools import ToolError
from minisweagent.tools.skills import SkillConfig, discover_skills

COMMANDS = {
    "/skill": "Choose task skills",
    "/mcp": "Choose configured MCP services",
    "/plugin": "Choose installed and enabled plugins",
    "/model": "Choose a configured model profile",
    "/subagent": "Choose a configured role and optional task",
    "/permissions": "Choose execution policy and sandbox",
    "/new": "Start a new conversation",
    "/stop": "Stop the current task",
    "/help": "Show commands",
}


class TerminalConfig(BaseModel):
    """Optional named model profiles; values follow the existing model configuration schema."""

    model_config = ConfigDict(extra="forbid")
    models: dict[str, dict] = Field(default_factory=dict)


@dataclass(frozen=True)
class InputResult:
    """A command result for terminal/desktop rendering; task text is never a shell command."""

    kind: str
    message: str = ""
    task: str = ""


class TerminalSession:
    """Own session-local choices; changes apply to the next runtime/task only.

    Commands never install plugins, start MCP, query models or write global config.
    An input beginning // escapes slash interpretation. File references are read
    when an actual task is submitted. Exceptions report invalid choices unchanged.
    """

    def __init__(self, config: dict, workspace: Path):
        self.config = deepcopy(config)
        self.files = ProjectFiles(workspace)
        self.settings = TerminalConfig.model_validate(config.get("terminal", {}))
        self.skills: list[str] = []
        self.mcp: list[str] | None = None
        self.role: str | None = None
        mode = config.get("agent", {}).get("mode", "confirm")
        self.permission = "auto" if mode == "yolo" else "human" if mode == "human" else "confirm"
        if config.get("permissions", {}).get("mode") == "read-only":
            self.permission = "readonly"

    def catalog(self, command: str) -> list[dict]:
        """Return safe names/descriptions without opening external services or exposing secrets."""
        plugins = load_plugins(self.config) if command in {"/skill", "/mcp", "/subagent"} else None
        if command == "/skill":
            catalog = discover_skills(SkillConfig.model_validate(self.config.get("skills", {})), self.files.root)
            catalog.update(plugins.skills)
            return [{"name": name, "description": skill.description} for name, skill in sorted(catalog.items())]
        if command == "/mcp":
            return [
                {"name": name, "description": "Configured MCP service"}
                for name in sorted(plugins.config.get("mcp_servers", {}))
            ]
        if command == "/plugin":
            settings = PluginConfig.model_validate(self.config.get("plugins", {}))
            return [
                {"name": name, "description": "Enabled installed plugin"}
                for name, value in sorted(PluginManager(settings.directory).list_plugins().items())
                if value["enabled"]
            ]
        if command == "/subagent":
            return [
                {"name": name, "description": value["description"]}
                for name, value in sorted(plugins.config.get("subagents", {}).get("roles", {}).items())
            ]
        if command == "/model":
            return [
                {"name": "current", "description": self.config.get("model", {}).get("model_name", "Unconfigured")},
                *[
                    {"name": name, "description": value.get("model_name", "Unconfigured")}
                    for name, value in sorted(self.settings.models.items())
                ],
            ]
        if command == "/permissions":
            return [
                {"name": name, "description": description}
                for name, description in (
                    ("readonly", "No Bash or external MCP; file context, skills and configured web reads"),
                    ("confirm", "Confirm actions before execution"),
                    ("auto", "Execute within the selected runtime policy"),
                )
            ]
        return []

    def process(self, text: str) -> InputResult:
        """Interpret one user message, validating an entire selection before mutation."""
        if not text.strip():
            return InputResult("message")
        if not text.startswith("/") or text.startswith("//"):
            return InputResult("task", task=self.prepare_task(text[1:] if text.startswith("//") else text))
        values = text.split(maxsplit=1)
        command, argument = values[0], values[1] if len(values) == 2 else ""
        if command not in COMMANDS:
            raise ToolError("Unknown command. Use /help, or // to send a literal leading slash.")
        if command == "/help":
            return InputResult(
                "message",
                "\n".join(f"{name}  {description}" for name, description in COMMANDS.items())
                + '\n@path or @"path with spaces": attach project files. Tab: choose; Esc Enter: submit.',
            )
        if command in {"/stop", "/new"}:
            if argument.strip():
                raise ToolError(f"{command} takes no arguments.")
            return InputResult(command[1:], "Current task stopped." if command == "/stop" else "New conversation.")
        if not argument.strip():
            rows = self.catalog(command)
            return InputResult(
                "message",
                json.dumps(rows, ensure_ascii=False)
                + "\nChoose names separated by commas; all/none clears or restores a selection where applicable.",
            )
        if command == "/permissions":
            values = argument.split()
            if (
                len(values) > 2
                or values[0] not in {"readonly", "confirm", "auto"}
                or len(values) == 2
                and values[1] not in {"local", "docker", "bubblewrap", "auto"}
            ):
                raise ToolError("Use /permissions readonly|confirm|auto [local|docker|bubblewrap|auto].")
            self.permission = values[0]
            if len(values) == 2:
                self.config.setdefault("sandbox", {})["mode"] = values[1]
            return InputResult("message", "Permissions selected; applies to the next task.")
        if command == "/model":
            name = argument.strip()
            if name == "current":
                return InputResult("message", "Current model retained.")
            if name not in self.settings.models or not self.settings.models[name].get("model_name"):
                raise ToolError("Choose a model profile listed by /model; configure terminal.models first.")
            self.config["model"] = deepcopy(self.settings.models[name])
            return InputResult("message", f"Model profile {name!r} selected for the next task.")
        if command == "/subagent":
            values = argument.split(maxsplit=1)
            if not values or not values[0] or values[0] == "none" and len(values) > 1:
                raise ToolError("Use /subagent ROLE [task], or /subagent none.")
            name = values[0]
            if name == "none":
                self.role = None
            elif name not in {row["name"] for row in self.catalog(command)}:
                raise ToolError("Choose a role listed by /subagent.")
            else:
                self.role = name
            return (
                InputResult("task", task=self.prepare_task(values[1]))
                if len(values) > 1
                else InputResult("message", "Role selected for the next task.")
            )
        names = list(dict.fromkeys(name.strip() for name in argument.split(",") if name.strip()))
        if not names:
            raise ToolError(f"Choose names listed by {command}, or none.")
        available = {row["name"] for row in self.catalog(command)}
        selected = sorted(available) if names == ["all"] else [] if names == ["none"] else names
        if set(selected) - available:
            raise ToolError(f"Choose available names listed by {command}.")
        if command == "/skill":
            self.skills = selected
        elif command == "/mcp":
            self.mcp = selected
        else:
            self.config.setdefault("plugins", {})["names"] = selected
        return InputResult("message", f"{command} selection saved for the next task: {', '.join(selected) or 'none'}.")

    def runtime_config(self) -> dict:
        """Build a detached per-task config; filter MCP after plugin expansion."""
        config = deepcopy(self.config)
        policy = {"readonly": "read-only", "human": "standard"}.get(self.permission, self.permission)
        config["permissions"] = {"mode": policy}
        mode = {"auto": "yolo", "human": "human"}.get(self.permission, "confirm")
        config.setdefault("agent", {})["mode"] = mode
        interactive = {
            "default": "interactive",
            "stateful": "stateful_interactive",
            "hindsight": "hindsight_interactive",
        }
        agent_class = config["agent"].get("agent_class")
        if agent_class in interactive:
            config["agent"]["agent_class"] = interactive[agent_class]
        if self.mcp is not None:
            config["mcp_selection"] = list(self.mcp)
        return config

    def prepare_task(self, text: str) -> str:
        """Attach explicit files and selected skill/role context, without running tools."""
        text = self.files.attach(text)
        if self.skills:
            plugins = load_plugins(self.config)
            catalog = discover_skills(SkillConfig.model_validate(self.config.get("skills", {})), self.files.root)
            catalog.update(plugins.skills)
            for name in self.skills:
                if name not in catalog:
                    raise ToolError(f"Selected skill is no longer available: {name!r}.")
                text += f"\n\nExplicitly selected skill {name!r}:\n" + catalog[name].view()["content"]
        if self.role:
            if self.role not in {row["name"] for row in self.catalog("/subagent")}:
                raise ToolError("Selected role is no longer available.")
            text += (
                "\n\nUser selected delegation: use subagent_run with role "
                + json.dumps(self.role)
                + " and the self-contained task above, then verify its result."
            )
        return text
