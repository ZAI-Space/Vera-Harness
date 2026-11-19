"""Interactive prompts, with console-free imports for redirected Windows commands."""

import os
import sys

from prompt_toolkit.formatted_text.html import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.plain_text import PlainTextOutput
from prompt_toolkit.shortcuts import PromptSession

from vera import global_config_dir

_history = FileHistory(global_config_dir / "interactive_history.txt")
_console_options = {}
if os.name == "nt":
    if not (sys.stdin and sys.stdin.isatty()):
        _console_options["input"] = DummyInput()
    if not (sys.stdout and sys.stdout.isatty()):
        _console_options["output"] = PlainTextOutput(sys.stdout) if sys.stdout else DummyOutput()
prompt_session = PromptSession(history=_history, **_console_options)
_multiline_prompt_session = PromptSession(history=_history, multiline=True, **_console_options)


def _multiline_prompt() -> str:
    return _multiline_prompt_session.prompt(
        "",
        bottom_toolbar=HTML(
            "Submit message: <b fg='yellow' bg='black'>Esc, then Enter</b> | "
            "Navigate history: <b fg='yellow' bg='black'>Arrow Up/Down</b> | "
            "Search history: <b fg='yellow' bg='black'>Ctrl+R</b>"
        ),
    )
