"""Validate model capabilities and request options shared by configuration and execution."""

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelOptions(BaseModel):
    """Persist supported request options; empty sampling values inherit provider defaults."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)
    tool_call_limit: int = Field(default=500, alias="toolCallLimit", ge=1, le=10000)
    reasoning_parameter: str = Field(default="reasoning_effort", alias="reasoningParameter")
    reasoning_values: list[str] = Field(
        default_factory=lambda: ["default", "off", "low", "medium", "high"], alias="reasoningValues", max_length=32
    )
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, alias="topP", ge=0, le=1)
    top_k: int | None = Field(default=None, alias="topK", ge=1, le=100)

    @field_validator("reasoning_parameter")
    @classmethod
    def parameter_path(cls, value: str) -> str:
        """Allow JSON parameter paths without allowing credential or transport overrides."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", value) or value.split(".")[0] in {
            "api_key",
            "api_base",
            "base_url",
            "model",
            "messages",
            "tools",
            "headers",
            "authorization",
            "stream",
            "timeout",
            "num_retries",
        }:
            raise ValueError("Use a reasoning parameter path, excluding credentials and transport settings.")
        return value

    @field_validator("reasoning_values")
    @classmethod
    def reasoning_choices(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 64 for value in values):
            raise ValueError("Thinking values must contain 1–64 characters.")
        return list(dict.fromkeys(values))


class ModelDefinition(BaseModel):
    """One configured model; capabilities are descriptive, request settings are executable."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(min_length=1, max_length=256)
    name: str | None = Field(default=None, max_length=64)
    reasoning: bool | None = None
    image_input: bool | None = Field(default=None, alias="imageInput")
    context_window: int | None = Field(default=None, alias="contextWindow", ge=1)
    max_tokens: int | None = Field(default=None, alias="maxTokens", ge=1)
    thinking_level_map: dict[str, str | None] | None = Field(default=None, alias="thinkingLevelMap")
    advanced: ModelOptions | None = None


def endpoint_base(address: str, protocol: str, full_url: bool = False) -> str:
    """Validate an API endpoint; complete standard operation URLs normalize to an SDK base URL."""
    address = address.strip().rstrip("/")
    url = urlsplit(address)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("请填写有效的 HTTP(S) API 地址，地址中不能包含密钥。")
    if full_url:
        suffix = {
            "openai-completions": "/chat/completions",
            "openai-responses": "/responses",
            "anthropic-messages": "/messages",
        }.get(protocol)
        if not suffix or not url.path.endswith(suffix):
            raise ValueError("完整 URL 须包含所选协议的标准请求路径。")
        address = address.removesuffix(suffix)
    return address


def is_local_endpoint(address: str) -> bool:
    """Only loopback custom providers may be configured without a credential."""
    return urlsplit(address).hostname in {"127.0.0.1", "localhost", "::1"}


def documented_capabilities(address: str, model: str) -> dict:
    """Fallback for official endpoints whose model listing omits capabilities.

    Source: https://docs.z.ai/guides/llm/glm-5.3 and /guides/vlm/glm-5.3-flash.
    Compatible relays retain their explicitly configured capabilities.
    """
    if urlsplit(address).hostname == "api.z.ai" and model in {"glm-5.3", "glm-5.3-flash"}:
        return {
            "reasoning": True,
            "reasoningValues": ["default", "low", "high", "max"],
            "imageInput": model == "glm-5.3-flash",
            "contextWindow": 1048576,
            "maxTokens": 131072,
        }
    return {}


def thinking_parameters(address: str, parameter: str, level: str) -> dict:
    """Map the UI's off/default intentions to the selected protocol's actual request values."""
    if level == "default":
        return {}
    host = urlsplit(address).hostname
    if level == "off" and host == "api.z.ai":
        return {"thinking": {"type": "disabled"}}
    if level == "off" and host in {"api.deepseek.com", "api.openai.com"}:
        level = "none"
    kwargs = {}
    apply_reasoning(kwargs, parameter, level)
    return kwargs


def apply_reasoning(kwargs: dict, parameter: str, level: str) -> None:
    """Write the validated dotted parameter path into a live request dictionary."""
    ModelOptions(reasoningParameter=parameter)
    target = kwargs
    parts = parameter.split(".")
    for name in parts[:-1]:
        target = target.setdefault(name, {})
        if not isinstance(target, dict):
            raise ValueError("Thinking parameter conflicts with another request option.")
    target[parts[-1]] = level
