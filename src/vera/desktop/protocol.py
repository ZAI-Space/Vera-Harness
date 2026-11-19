"""Worker frames on reserved stdout; logs belong on stderr."""

import json
import sys
from contextlib import contextmanager
from contextvars import ContextVar

parent_tool_call = ContextVar("desktop_parent_tool_call", default=None)


@contextmanager
def delegated_output(call_id):
    """Tag child model output so it never overwrites the parent's live reply."""
    token = parent_tool_call.set(call_id)
    try:
        yield
    finally:
        parent_tool_call.reset(token)


def send(kind: str, **payload) -> None:
    """Flush one JSON frame immediately so a model delta can reach the desktop."""
    if parent := parent_tool_call.get():
        payload["parentToolCallId"] = parent
    sys.__stdout__.write(json.dumps({"type": kind, **payload}, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()
