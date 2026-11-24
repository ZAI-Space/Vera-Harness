"""Normalize provider-reported tokens without requiring model prices."""


def token_usage(raw: dict) -> dict:
    """Normalize OpenAI/Responses/Anthropic/DeepSeek counters, preserving unknown cache coverage."""
    details = raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    cached = next(
        (
            value
            for value in (
                details.get("cached_tokens"),
                raw.get("cache_read_input_tokens"),
                raw.get("prompt_cache_hit_tokens"),
            )
            if value is not None
        ),
        None,
    )
    written = int(raw.get("cache_creation_input_tokens", details.get("cache_write_tokens", 0)) or 0)
    incoming = int(raw.get("prompt_tokens", raw.get("input_tokens", 0)) or 0)
    # Native Anthropic input excludes cache reads/writes; normalized prompt_tokens already includes them.
    if "prompt_tokens" not in raw and ("cache_read_input_tokens" in raw or "cache_creation_input_tokens" in raw):
        incoming += int(cached or 0) + written
    outgoing = int(raw.get("completion_tokens", raw.get("output_tokens", 0)) or 0)
    return {
        "input": max(0, incoming),
        "output": max(0, outgoing),
        "cacheRead": max(0, int(cached or 0)),
        "cacheWrite": max(0, written),
        "cacheReported": cached is not None,
        "totalTokens": max(0, incoming + outgoing),
    }
