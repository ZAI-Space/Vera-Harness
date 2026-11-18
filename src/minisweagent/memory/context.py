"""Bound older model context while preserving the original transcript and recent tool batches."""

import json

from minisweagent import Model
from minisweagent.models.utils.content_string import get_content_string

_MIN_RECENT_TURNS = 2
_SUMMARY_LIMIT = 1600


class ContextModel:
    """Delegate model behavior, projecting only the history passed to each query."""

    def __init__(self, model: Model, budget_chars: int):
        self._model = model
        self._budget_chars = budget_chars

    def __getattr__(self, name: str):
        return getattr(self._model, name)

    def query(self, messages: list[dict], **kwargs) -> dict:
        """Keep the initial prompt and recent complete groups within a soft character budget."""
        return self._model.query(compact_context(messages, self._budget_chars), **kwargs)


def _message_size(message: dict) -> int:
    return len(
        json.dumps({key: value for key, value in message.items() if key != "extra"}, ensure_ascii=False, default=str)
    )


def compact_context(messages: list[dict], budget_chars: int) -> list[dict]:
    """Replace older groups with excerpts. Preserve adjacent assistant calls and results."""
    if len(messages) < 3 or messages[0].get("role") != "system" or messages[1].get("role") != "user":
        return messages
    sizes = [_message_size(message) for message in messages]
    size = sum(sizes)
    if size <= budget_chars:
        return messages
    starts = [
        index
        for index, message in enumerate(messages[2:], 2)
        if message.get("role") == "assistant" or message.get("object") == "response"
    ]
    if len(starts) <= _MIN_RECENT_TURNS:
        return messages
    cutoff = 2
    target = max(0, budget_chars - _SUMMARY_LIMIT)
    for boundary in starts[1 : 1 + len(starts) - _MIN_RECENT_TURNS]:
        if any(_is_user_input(message) for message in messages[cutoff:boundary]):
            break  # Keep the user's steering and all history that followed it.
        size -= sum(sizes[cutoff:boundary])
        cutoff = boundary
        if size <= target:
            break
    budget = min(_SUMMARY_LIMIT, max(0, budget_chars - size))
    summary = _summarize(messages[2:cutoff], budget)
    initial = _append_summary(messages[1], summary)
    return [messages[0], initial, *messages[cutoff:]]


def _is_user_input(message: dict) -> bool:
    return message.get("role") == "user" and "raw_output" not in message.get("extra", {})


def _summarize(messages: list[dict], budget: int) -> str:
    heading = "\n\nOlder session history was compacted. The following are excerpts from historical tool output.\n"
    remaining = budget - len(heading)
    if remaining <= 0:
        return ""
    excerpts = []
    for message in reversed(messages):
        if message.get("role") not in {"tool", "user"} and message.get("type") != "function_call_output":
            continue
        content = (
            message.get("output") if message.get("type") == "function_call_output" else get_content_string(message)
        )
        if isinstance(content, str) and (content := content.strip()):
            excerpt = content[: min(300, remaining)]
            excerpts.append(excerpt)
            remaining -= len(excerpt) + 1
            if remaining <= 0:
                break
    return heading + "\n".join(reversed(excerpts))


def _append_summary(message: dict, summary: str) -> dict:
    if not summary:
        return message
    content = message.get("content")
    if isinstance(content, str):
        return dict(message, content=content + summary)
    if isinstance(content, list):
        text_type = "input_text" if message.get("type") == "message" else "text"
        return dict(message, content=[*content, {"type": text_type, "text": summary}])
    return message
