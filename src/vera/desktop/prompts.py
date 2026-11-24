"""Keep legacy desktop conversation history compatible with the general assistant policy."""

from jinja2 import StrictUndefined, Template

from vera.config import get_config_from_spec


def refresh_legacy_history(messages: list[dict], variables: dict) -> list[dict]:
    """Remove only an exact legacy task-template wrapper, retaining its original task text.

    Ordinary user content, tool results and custom prompts remain intact. The
    old template is rendered with live environment facts and must match in full.
    """
    template = get_config_from_spec("vera.yaml")["agent"]["instance_template"]
    prefix, separator, suffix = template.partition("{{task}}")
    if not separator:
        return messages
    suffix = Template(suffix, undefined=StrictUndefined).render(**variables)
    result = []
    for message in messages:
        content = message.get("content")
        if (
            message.get("role") == "user"
            and isinstance(content, str)
            and content.startswith(prefix)
            and content.endswith(suffix)
        ):
            message = message | {"content": content[len(prefix) : -len(suffix) if suffix else None]}
        result.append(message)
    return result
