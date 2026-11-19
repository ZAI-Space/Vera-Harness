"""Private provider configuration and safe model catalogs for the desktop."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

import requests

from vera.channels.credentials import CredentialStore


@lru_cache(maxsize=1)
def local_model_catalog():
    """Read the installed LiteLLM catalog without importing its network-initializing module."""
    specification = find_spec("litellm")
    if specification is None or not specification.origin:
        return {}
    path = Path(specification.origin).parent / "model_prices_and_context_window_backup.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


class Providers:
    """Keep credentials in a private file; catalogs return only presence metadata."""

    def __init__(self, store):
        self.store = store
        self.path = store.directory / "provider-credentials.json"
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

    def list(self) -> list[dict]:
        values = self.store.get("settings", "providers", {})
        for name in ("openai", "anthropic", "deepseek", "openrouter", "gemini"):
            catalog = []
            for identifier, metadata in local_model_catalog().items():
                if metadata.get("litellm_provider") == name and metadata.get("mode") == "chat":
                    model_id = identifier.removeprefix(name + "/")
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
            key = keys.get(name) or os.getenv(name.upper() + "_API_KEY")
            result.append(
                provider
                | {
                    "customModels": provider["models"] if provider.get("custom") else [],
                    "configured": bool(key),
                    "authType": "api_key" if key else None,
                    "authSource": "stored" if name in keys else "environment" if key else None,
                }
            )
        return result

    def models(self) -> list[dict]:
        return [
            {
                "provider": provider["id"],
                "providerName": provider["name"],
                "id": model["id"],
                "label": model.get("name", model["id"]),
                "name": model.get("name", model["id"]),
                "authed": provider["configured"],
                "contextWindow": model.get("contextWindow", 0),
                "thinkingLevels": ["off", "low", "medium", "high"] if model.get("reasoning") else ["off"],
                "imageInput": model.get("imageInput", False),
            }
            for provider in self.list()
            for model in provider["models"]
        ]

    def configure(self, value: dict) -> None:
        """Save a validated custom provider, excluding its optional credential."""
        from urllib.parse import urlsplit

        value = value.copy()
        key = value.pop("apiKey", None)
        address = urlsplit(value["baseUrl"])
        if address.scheme not in {"https", "http"} or not address.hostname or address.username or address.password:
            raise ValueError("Provider URL must be HTTP(S) without embedded credentials.")
        if value["api"] not in {"openai-completions", "openai-responses", "anthropic-messages", "google-generative-ai"}:
            raise ValueError("This provider protocol is not supported by the VERA adapter.")
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
        key = self.credentials().get(provider["id"]) or os.getenv(provider["id"].upper() + "_API_KEY")
        kwargs = {"timeout": 90, "num_retries": 0}
        if key:
            kwargs["api_key"] = key
        if provider.get("baseUrl"):
            kwargs["api_base"] = provider["baseUrl"]
        name = model["modelId"]
        prefix = (
            {"anthropic-messages": "anthropic", "google-generative-ai": "gemini"}.get(provider.get("api"), "openai")
            if provider.get("custom")
            else provider["id"]
        )
        return {
            "model_class": "litellm_response" if provider.get("api") == "openai-responses" else "litellm",
            "model_name": f"{prefix}/{name}",
            "model_kwargs": kwargs,
        }

    def upstream(self, value: dict) -> dict:
        """Read the selected provider's /models without sending keys to redirects."""
        address = value["baseUrl"].rstrip("/")
        provider = value.get("providerId", "")
        key = value.get("apiKey") or self.credentials().get(provider) or os.getenv(provider.upper() + "_API_KEY")
        response = requests.get(
            address + "/models",
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=20,
            allow_redirects=False,
        )
        response.raise_for_status()
        models = [
            {"id": item["id"], "name": item.get("name", item["id"])}
            for item in response.json().get("data", [])
            if isinstance(item.get("id"), str)
        ]
        return {"models": models, "baseUrl": address}
