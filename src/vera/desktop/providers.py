"""Private provider configuration and safe model catalogs for the desktop."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

import requests

from vera.channels.credentials import CredentialStore
from vera.desktop.model_settings import (
    ModelDefinition,
    documented_capabilities,
    endpoint_base,
    is_local_endpoint,
    thinking_parameters,
)


def reported_capabilities(model: dict) -> dict:
    """Read provider-declared limits; SDK catalogs are fallback descriptions, not request budgets."""
    result = {}
    for field, source in (("contextWindow", "context_window"), ("maxTokens", "max_output_tokens")):
        value = model.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            result[field] = value
    if isinstance(model.get("input_modalities"), list):
        result["imageInput"] = "image" in model["input_modalities"]
    effort = model.get("effort", {})
    levels = effort.get("supported_levels") if isinstance(effort, dict) else None
    if isinstance(levels, list) and all(isinstance(level, str) and 0 < len(level) <= 64 for level in levels):
        result["reasoning"] = bool(levels)
        result["reasoningValues"] = list(dict.fromkeys(["default", "off", *levels]))
    return result


@lru_cache(maxsize=1)
def local_model_catalog():
    """Read the installed LiteLLM catalog without importing its network-initializing module."""
    specification = find_spec("litellm")
    if specification is None or not specification.origin:
        return {}
    path = Path(specification.origin).parent / "model_prices_and_context_window_backup.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


@lru_cache(maxsize=1)
def model_capabilities() -> dict:
    """Index local metadata once; model discovery never performs per-model network lookups."""
    result = {}
    for identifier, metadata in local_model_catalog().items():
        for name in (identifier, identifier.split("/", 1)[-1]):
            result.setdefault(name, metadata)
    return result


def restore_model_config(config: dict, state_dir: str, provider_ref: dict) -> None:
    """Restore a desktop provider credential only in the live worker config."""
    from vera.desktop.store import DesktopStore

    persisted_model = config.get("model", {})
    providers = Providers(DesktopStore(Path(state_dir)))
    live_model = providers.model_config(provider_ref)
    live_model["model_kwargs"].update(persisted_model.get("model_kwargs", {}))
    for name in (
        "allow_text_final",
        "cost_tracking",
        "format_error_template",
        "observation_template",
        "multimodal_regex",
    ):
        if name in persisted_model:
            live_model[name] = persisted_model[name]
    config["model"] = live_model
    for name, reference in config.pop("desktop_subagent_refs", {}).items():
        role = config.get("subagents", {}).get("roles", {}).get(name)
        if role is not None:
            role["model"] = providers.model_config(reference)


class Providers:
    """Keep credentials in a private file; catalogs return only presence metadata."""

    def __init__(self, store):
        self.store = store
        self.vault = CredentialStore(store.directory)

    def credentials(self) -> dict:
        return self.vault.load("desktop-providers") if self.vault._path("desktop-providers").exists() else {}

    def save_key(self, provider: str, key: str | None) -> None:
        values = self.credentials()
        if key:
            values[provider] = key
        else:
            values.pop(provider, None)
        self.vault.save("desktop-providers", values)

    def key(self, provider: dict) -> str | None:
        """Resolve a stored credential or the selected manufacturer's environment key."""
        name = {"chatgpt": "openai", "claude": "anthropic", "kimi": "moonshot"}.get(
            provider.get("template"), provider.get("template") or provider["id"]
        )
        return self.credentials().get(provider["id"]) or os.getenv(name.upper().replace("-", "_") + "_API_KEY")

    def list(self) -> list[dict]:
        values = self.store.get("settings", "providers", {})
        for name in ("openai", "anthropic", "deepseek", "openrouter", "gemini"):
            catalog = []
            identifiers = set()
            for identifier, metadata in local_model_catalog().items():
                if metadata.get("litellm_provider") == name and metadata.get("mode") == "chat":
                    model_id = identifier.removeprefix(name + "/")
                    if model_id in identifiers:
                        continue
                    identifiers.add(model_id)
                    catalog.append(
                        {
                            "id": model_id,
                            "name": model_id,
                            "contextWindow": metadata.get("max_input_tokens", 0),
                            "reasoning": bool(metadata.get("supports_reasoning")),
                            "imageInput": bool(metadata.get("supports_vision")),
                        }
                    )
            values.setdefault(
                name, {"id": name, "name": name, "custom": False, "models": catalog[:250], "api": "openai-completions"}
            )
        keys = self.credentials()
        result = []
        for name, provider in values.items():
            key = self.key(provider)
            result.append(
                provider
                | {
                    "customModels": provider["models"] if provider.get("custom") else [],
                    "configured": bool(key)
                    or bool(provider.get("custom") and is_local_endpoint(provider.get("baseUrl", ""))),
                    "authType": "api_key" if key else None,
                    "authSource": "stored" if name in keys else "environment" if key else None,
                }
            )
        return result

    def models(self) -> list[dict]:
        """Expose only authenticated, visible models to execution pickers."""
        preferences = self.store.get("settings", "modelPrefs", {})
        return [
            {
                "provider": provider["id"],
                "providerName": provider["name"],
                "id": model["id"],
                "label": model["id"],
                "name": model["id"],
                "authed": provider["configured"],
                "contextWindow": model.get("contextWindow", 0),
                "thinkingLevels": (
                    documented_capabilities(provider.get("baseUrl", ""), model["id"]).get("reasoningValues")
                    or model.get("advanced", {}).get("reasoningValues")
                    or ["default", "off", "low", "medium", "high"]
                )
                if model.get("reasoning")
                else ["off"],
                "imageInput": model.get("imageInput", False),
            }
            for provider in self.list()
            if provider["configured"]
            for model in provider["models"]
            if (
                model["id"] in preferences.get("visibleModels", {}).get(provider["id"], [])
                if provider["id"] in preferences.get("hiddenProviders", [])
                else model["id"] not in preferences.get("hiddenModels", {}).get(provider["id"], [])
            )
        ]

    def configure(self, value: dict) -> None:
        """Save a validated custom provider, excluding its optional credential."""
        value = value.copy()
        key = value.pop("apiKey", None)
        if value["api"] not in {"openai-completions", "openai-responses", "anthropic-messages", "google-generative-ai"}:
            raise ValueError("This provider protocol is not supported by the VERA adapter.")
        value["requestUrl"] = value["baseUrl"].strip().rstrip("/")
        value["baseUrl"] = endpoint_base(value["baseUrl"], value["api"], value.get("fullUrl", False))
        value["models"] = [
            ModelDefinition.model_validate(model).model_dump(by_alias=True, exclude_none=True)
            for model in value["models"]
        ]
        reported = self.store.get("model_capabilities", value["baseUrl"], {})
        for model in value["models"]:
            limits = documented_capabilities(value["baseUrl"], model["id"]) | reported.get(model["id"], {})
            for field in ("contextWindow", "maxTokens"):
                if model.get(field) and limits.get(field) and model[field] > limits[field]:
                    raise ValueError(f"模型 {model['id']} 的 {field} 不能超过服务商声明的 {limits[field]} Token。")
            if model.get("imageInput") and limits.get("imageInput") is False:
                raise ValueError(f"服务商声明模型 {model['id']} 不支持图片输入。")
            metadata = model_capabilities().get(model["id"], {})
            for field, source in (
                ("contextWindow", "max_input_tokens"),
                ("reasoning", "supports_reasoning"),
                ("imageInput", "supports_vision"),
            ):
                if field not in model and source in metadata and metadata[source] is not None:
                    model[field] = metadata[source]
        value["name"] = value.get("name") or value["id"]
        if len({model["id"] for model in value["models"]}) != len(value["models"]):
            raise ValueError("模型 ID 不能重复。")
        values = self.store.get("settings", "providers", {})
        values[value["id"]] = value | {"custom": True}
        self.store.save("settings", "providers", values)
        if key:
            self.save_key(value["id"], key)

    def model_config(self, model: dict | None) -> dict:
        if not model:
            raise ValueError("Configure and select a model before sending a task.")
        provider = next((item for item in self.list() if item["id"] == model["provider"]), None)
        if provider is None:
            raise ValueError("Selected provider no longer exists.")
        key = self.key(provider)
        if not key and not (provider.get("custom") and is_local_endpoint(provider.get("baseUrl", ""))):
            raise ValueError("Configure the selected provider's API key before sending a task.")
        if model["modelId"] not in {item["id"] for item in provider["models"]}:
            raise ValueError("Selected model is no longer configured.")
        kwargs = {"timeout": 90, "num_retries": 0}
        if provider.get("api") == "openai-responses":
            # The user chose this endpoint explicitly. A new model alias must not
            # make LiteLLM silently route it through Chat Completions instead.
            kwargs["model_info"] = {"supported_endpoints": ["/v1/responses"]}
        kwargs["api_key"] = key or "local-no-key"
        if provider.get("baseUrl"):
            kwargs["api_base"] = provider["baseUrl"]
        definition = self.definition(model)
        if provider.get("custom") and provider.get("template", "custom") == "custom":
            # Explicit custom capabilities may describe a compatible relay which
            # supports parameters absent from LiteLLM's built-in model metadata.
            options = definition.get("advanced", {})
            allowed = []
            if (
                definition.get("reasoning")
                and options.get("reasoningParameter", "reasoning_effort") == "reasoning_effort"
            ):
                allowed.append("reasoning_effort")
            if options.get("topK") is not None:
                allowed.append("top_k")
            if allowed:
                kwargs["allowed_openai_params"] = allowed
        if definition.get("maxTokens"):
            kwargs["max_output_tokens" if provider.get("api") == "openai-responses" else "max_tokens"] = definition[
                "maxTokens"
            ]
        for field, parameter in (("temperature", "temperature"), ("topP", "top_p"), ("topK", "top_k")):
            if definition.get("advanced", {}).get(field) is not None:
                kwargs[parameter] = definition["advanced"][field]
        name = model["modelId"]
        prefix = (
            {"anthropic-messages": "anthropic", "google-generative-ai": "gemini"}.get(provider.get("api"), "openai")
            if provider.get("custom")
            else provider["id"]
        )
        return {
            "model_class": "litellm_response" if provider.get("api") == "openai-responses" else "litellm",
            "cost_tracking": "tokens",
            "allow_text_final": True,
            "usage_identity": {"provider": provider["id"], "modelId": name},
            "model_name": f"{prefix}/{name}",
            "model_kwargs": kwargs,
        }

    def definition(self, reference: dict) -> dict:
        """Read a configured model's canonical capabilities and request preferences."""
        provider = next((item for item in self.list() if item["id"] == reference["provider"]), {})
        return next((item for item in provider.get("models", []) if item["id"] == reference["modelId"]), {})

    def reasoning_kwargs(self, reference: dict, level: str, options: dict) -> dict:
        """Reject unavailable choices and preserve the distinction between default and disabled."""
        provider = next((item for item in self.list() if item["id"] == reference["provider"]), None)
        if provider is None:
            raise ValueError("Selected provider no longer exists.")
        model = self.definition(reference)
        if not model.get("reasoning") and level in {"off", "default"}:
            return {}
        address = provider.get("baseUrl", "")
        if not address and not provider.get("custom") and provider["id"] == "openai":
            # Built-in OpenAI lets the SDK choose its default endpoint.
            address = "https://api.openai.com/v1"
        capabilities = documented_capabilities(address, reference["modelId"])
        levels = capabilities.get("reasoningValues") or options["reasoningValues"]
        if level not in levels:
            raise ValueError("所选模型不支持此思考强度，请重新选择。")
        return thinking_parameters(address, options["reasoningParameter"], level)

    def upstream(self, value: dict) -> dict:
        """Discover models with the chosen protocol; report actionable errors without secrets."""
        from urllib.parse import urlsplit

        protocol = value.get("api", "openai-completions")
        address = endpoint_base(value.get("baseUrl", ""), protocol, value.get("fullUrl", False))
        url = urlsplit(address)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("请填写有效的 HTTP(S) API 地址，地址中不能包含密钥。")
        provider = value.get("providerId", "")
        key = value.get("apiKey") or self.key({"id": provider, "template": value.get("template")})
        if not key and not is_local_endpoint(address):
            raise ValueError("请先填写 API 密钥，再自动获取模型列表。")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        if protocol == "anthropic-messages":
            headers = {"anthropic-version": "2023-06-01", **({"x-api-key": key} if key else {})}
        elif protocol == "google-generative-ai":
            headers = {"x-goog-api-key": key} if key else {}
        suffix = (
            "/v1" if protocol == "anthropic-messages" else "/v1beta" if protocol == "google-generative-ai" else "/v1"
        )
        candidates = [address]
        if not url.path.strip("/"):
            candidates.append(address + suffix)
        try:
            for candidate in candidates:
                response = requests.get(candidate + "/models", headers=headers, timeout=20, allow_redirects=False)
                if response.status_code != 404:
                    address = candidate
                    break
            if response.status_code in {401, 403}:
                raise ValueError("模型列表鉴权失败，请检查 API Key、所属地区和账号权限。")
            if response.status_code in {404, 405}:
                raise ValueError("此接口未提供模型列表，请检查 API 地址或使用手动添加模型。")
            if response.status_code == 429:
                raise ValueError("服务商暂时限流，请稍后重试或手动添加模型。")
            if response.is_redirect:
                raise ValueError("API 地址发生跳转；为避免泄露密钥，请填写服务商的最终 API 地址。")
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.JSONDecodeError:
            raise ValueError("模型接口未返回有效 JSON，请检查 API 地址。") from None
        except requests.HTTPError:
            raise ValueError(
                f"模型列表请求失败（HTTP {response.status_code}），请检查 API 地址或服务商状态。"
            ) from None
        except requests.RequestException:
            raise ValueError("无法连接模型服务，请检查 API 地址、网络或代理后重试。") from None
        if not isinstance(result, dict):
            raise ValueError("模型接口返回格式不正确；可使用手动添加。")
        catalog = result.get("data", result.get("models", []))
        if not isinstance(catalog, list):
            raise ValueError("模型接口返回的列表格式不正确；可使用手动添加。")
        entries = [
            item for item in catalog if isinstance(item, dict) and isinstance(item.get("id") or item.get("name"), str)
        ]
        models = [
            {
                "id": item.get("id") or item["name"].removeprefix("models/"),
                "name": item.get("displayName") or item.get("id") or item["name"],
            }
            for item in entries
        ]
        catalog = model_capabilities()
        reported = {}
        for model, item in zip(models, entries):
            metadata = catalog.get(model["id"], {})
            for field, source in (
                ("contextWindow", "max_input_tokens"),
                ("reasoning", "supports_reasoning"),
                ("imageInput", "supports_vision"),
            ):
                if source in metadata and metadata[source] is not None:
                    model[field] = metadata[source]
            capabilities = documented_capabilities(address, model["id"]) | reported_capabilities(item)
            model.update(capabilities)
            if capabilities:
                reported[model["id"]] = capabilities
        self.store.save("model_capabilities", address, reported)
        return {"models": models, "baseUrl": address}
