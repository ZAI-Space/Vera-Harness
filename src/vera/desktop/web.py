"""Configure desktop web tools without exposing credentials in settings or trajectories."""

import os
import time
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from vera.channels.credentials import CredentialStore
from vera.tools import ToolError, ToolRegistry
from vera.tools.web import firecrawl_provider, register_web_tools, searxng_provider, tavily_provider

VARIABLES = {"tavily": "TAVILY_API_KEY", "firecrawl": "FIRECRAWL_API_KEY", "searxng": "SEARXNG_URL"}


class WebSettingsInput(BaseModel):
    """A blank API key preserves the stored credential; removal must be explicit."""

    model_config = ConfigDict(extra="forbid", strict=True)
    provider: str
    enabled: bool
    readPages: bool = True
    apiKey: str = ""
    searxngUrl: str = ""
    removeKey: bool = False


class WebSettings:
    """Reuse runtime provider adapters and the desktop's OS-protected credential vault."""

    def __init__(self, store):
        self.store = store
        self.vault = CredentialStore(store.directory)

    def credentials(self) -> dict:
        return self.vault.load("desktop-web") if self.vault.has("desktop-web") else {}

    def status(self) -> dict:
        """Return only credential presence; runtime configuration contains no API key."""
        config = self.store.get("settings", "web", {})
        preferences = self.store.get("settings", "webPreferences", {})
        credentials = self.credentials()
        return {
            "provider": config.get("search_provider")
            or config.get("extract_provider")
            or preferences.get("provider", "tavily"),
            "enabled": bool(config.get("search_provider") or config.get("extract_provider")),
            "readPages": bool(config.get("extract_provider")) if config else preferences.get("readPages", True),
            "searxngUrl": preferences.get("searxngUrl", ""),
            "credentials": {
                name: bool(credentials.get(name) or os.getenv(variable)) for name, variable in VARIABLES.items()
            },
        }

    def save(self, arguments: dict) -> dict:
        """Validate everything before replacing config. Changes apply to subsequent tasks only."""
        try:
            value = WebSettingsInput.model_validate(arguments)
        except ValidationError:
            raise ValueError("联网设置格式无效，请检查服务、开关和凭据输入。") from None
        if value.provider not in VARIABLES:
            raise ValueError("请选择 Tavily、Firecrawl 或 SearXNG。")
        if value.provider == "searxng" and value.enabled and value.readPages:
            raise ValueError("SearXNG 仅支持搜索，请关闭网页正文读取。")
        credentials = self.credentials()
        if value.removeKey:
            credentials.pop(value.provider, None)
        elif value.apiKey.strip():
            credentials[value.provider] = value.apiKey.strip()
        address = value.searxngUrl.strip().rstrip("/")
        if address:
            parsed = urlsplit(address)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("SearXNG 地址须为不含密钥、查询参数的 HTTP(S) 实例地址。")
        if value.provider == "searxng":
            credentials["searxng"] = address
        if value.enabled and not (credentials.get(value.provider) or os.getenv(VARIABLES[value.provider])):
            raise ValueError("请先填写搜索服务的 API Key 或 SearXNG 地址。")
        config = (
            {"search_provider": value.provider, "extract_provider": value.provider if value.readPages else None}
            if value.enabled
            else {}
        )
        self.vault.save("desktop-web", credentials)
        self.store.save(
            "settings",
            "webPreferences",
            {"provider": value.provider, "readPages": value.readPages, "searxngUrl": address},
        )
        self.store.save("settings", "web", config)
        return self.status()

    def environment(self, config: dict) -> dict[str, str]:
        """Supply selected secrets only to an isolated worker's environment, never its persisted config."""
        credentials = self.credentials()
        result = {}
        for name in {config.get("search_provider"), config.get("extract_provider")} - {None}:
            if name not in VARIABLES:
                raise ValueError("Unknown web provider.")
            variable = VARIABLES[name]
            if value := credentials.get(name) or os.getenv(variable):
                result[variable] = value
            else:
                raise ValueError("联网工具凭据已缺失，请在设置中重新配置。")
        return result

    def test(self) -> dict:
        """Run saved search/extract adapters against fixed public documentation; consumes provider credits."""
        config = self.store.get("settings", "web", {})
        if not config:
            raise ValueError("请先保存并启用联网工具。")
        environment = self.environment(config)
        factories = {"tavily": tavily_provider, "firecrawl": firecrawl_provider, "searxng": searxng_provider}
        providers = {name: factories[name](environment[VARIABLES[name]]) for name in set(config.values()) - {None}}
        registry = ToolRegistry()
        register_web_tools(
            registry,
            search=providers.get(config.get("search_provider")),
            extract=providers.get(config.get("extract_provider")),
        )
        started = time.monotonic()
        actions = []
        if config.get("search_provider"):
            actions.append(("web_search", {"query": "Python official documentation", "limit": 2}))
        if config.get("extract_provider"):
            actions.append(("web_extract", {"url": "https://docs.python.org/3/"}))
        for name, arguments in actions:
            result = registry.execute({"tool": name, "arguments": arguments})
            if result["returncode"]:
                raise ToolError(result["exception_info"])
        return {
            "ok": True,
            "tools": [name for name, _ in actions],
            "durationMs": round((time.monotonic() - started) * 1000),
        }
