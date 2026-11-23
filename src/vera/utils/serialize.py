"""Merge configuration mappings while preserving explicit override semantics."""

from typing import Any

UNSET = object()


_SECRET_KEY_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "authorization",
    "headers",
}


def _is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.casefold().replace("-", "_")
    return normalized in _SECRET_KEY_NAMES or normalized.endswith(("_api_key", "_token", "_password", "_secret"))


def strip_sensitive(value: Any) -> Any:
    """Remove credentials while retaining validated MCP environment references."""
    if isinstance(value, dict):
        return {
            key: _mcp_header_references(value) if key == "headers_from" else strip_sensitive(item)
            for key, item in value.items()
            if not _is_secret_key(key)
        }
    if isinstance(value, list):
        return [strip_sensitive(item) for item in value]
    return value


def _mcp_header_references(value: dict) -> dict[str, str]:
    """Retain only header environment names from a valid complete MCP transport."""
    from pydantic import ValidationError

    from vera.tools.mcp import MCPServerConfig

    try:
        return MCPServerConfig.model_validate(value).headers_from.copy()
    except ValidationError:
        return {}


def recursive_merge(*dictionaries: dict | None) -> dict:
    """Merge multiple dictionaries recursively.

    Later dictionaries take precedence over earlier ones.
    Nested dictionaries are merged recursively.
    UNSET values are skipped.
    """
    if not dictionaries:
        return {}
    result: dict[str, Any] = {}
    for d in dictionaries:
        if d is None:
            continue
        for key, value in d.items():
            if value is UNSET:
                continue
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = recursive_merge(result[key], value)
            elif isinstance(value, dict):
                # Recursively merge dict values to filter out nested UNSET values
                result[key] = recursive_merge(value)
            else:
                result[key] = value
    return result
