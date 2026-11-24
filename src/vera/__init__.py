"""Expose package paths, version and structural interfaces for runtime adapters.

Importing this module creates the selected global configuration directory and
loads its .env file without replacing existing environment values. Protocols
describe adapter contracts for static checking; inheritance is not required.
"""

__version__ = "0.1.0a1"

import os
from pathlib import Path
from typing import Any, Protocol

import dotenv
from platformdirs import user_config_dir
from rich.console import Console

from vera.branding import APP_NAME, DOCUMENTATION_URL, apply_legacy_environment
from vera.utils.log import logger

package_dir = Path(__file__).resolve().parent


apply_legacy_environment()
default_config_dir = Path(user_config_dir("VERA", appauthor=False))
legacy_config_dir = Path(user_config_dir("mini-swe-agent"))
global_config_dir = Path(
    os.getenv("VERA_GLOBAL_CONFIG_DIR")
    or (legacy_config_dir if legacy_config_dir.is_dir() and not default_config_dir.exists() else default_config_dir)
)
global_config_dir.mkdir(parents=True, exist_ok=True)
global_config_file = Path(global_config_dir) / ".env"

if not os.getenv("VERA_SILENT_STARTUP"):
    Console().print(
        f"[bold cyan]{APP_NAME}[/bold cyan]  [dim]Agent Harness[/dim]  [bold green]v{__version__}[/bold green]\n"
        f"Docs: {DOCUMENTATION_URL}\n"
        f"Loading global config from [bold green]'{global_config_file}'[/bold green]",
    )
dotenv.load_dotenv(dotenv_path=global_config_file)
apply_legacy_environment()


class Model(Protocol):
    """Protocol for language models."""

    config: Any

    def query(self, messages: list[dict[str, str]], **kwargs) -> dict:
        """Query the configured provider and return an assistant message.

        Provider adapters can perform network requests and update usage counters.
        Parsing failures raise FormatError with the response and usage retained
        in its messages. Provider and configuration errors can propagate.
        """
        ...

    def format_message(self, **kwargs) -> dict:
        """Build a provider message from fields such as role and content.

        Accepted fields and multimodal conversion depend on the adapter.
        """
        ...

    def format_observation_messages(
        self, message: dict, outputs: list[dict], template_vars: dict | None = None
    ) -> list[dict]:
        """Convert ordered action outputs into provider observation messages.

        Pass the assistant message that requested the actions and matching
        outputs. Optional template variables customize observation rendering.
        """
        ...

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        """Return adapter variables for prompt templates; these can contain secrets."""
        ...

    def serialize(self) -> dict:
        """Return model metadata for trajectory merging; callers must redact secrets."""
        ...


class Environment(Protocol):
    """Protocol for execution environments."""

    config: Any

    def execute(self, action: dict, cwd: str = "") -> dict[str, Any]:
        """Execute an action in the configured environment, optionally overriding cwd.

        Actions can change files and process state. Results contain output and
        execution status; adapters define error details and timeout behavior.
        A recognized completion action can raise Submitted instead of returning.
        """
        ...

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        """Return environment template variables, which can include sensitive config."""
        ...

    def serialize(self) -> dict:
        """Return environment metadata for merging; callers must redact secrets."""
        ...


class Agent(Protocol):
    """Protocol for agents."""

    config: Any

    def run(self, task: str, **kwargs) -> dict:
        """Run the model/tool loop for task and return its termination information.

        Execution can change conversation, usage and environment state. Concrete
        agents define limits, interaction policy and propagated error behavior.
        """
        ...

    def save(self, path: Path | None, *extra_dicts) -> dict:
        """Return serialized trajectory data and write it when path is provided.

        Additional dictionaries merge into the trajectory. File errors propagate;
        concrete agents define merge precedence and redaction behavior.
        """
        ...


__all__ = [
    "Agent",
    "Model",
    "Environment",
    "package_dir",
    "__version__",
    "global_config_file",
    "global_config_dir",
    "logger",
]
