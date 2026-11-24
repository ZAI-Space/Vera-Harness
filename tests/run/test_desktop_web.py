"""Exercise desktop web persistence and real HTTP adapters without third-party credentials."""

import json
import os
import sqlite3

import pytest

from tests.run.test_web_tools import web_service  # noqa: F401
from vera.desktop.service import DesktopService
from vera.tools import ToolError


def test_private_credentials_preservation_validation_and_disable(tmp_path):
    service = DesktopService(tmp_path)
    try:
        assert not service.invoke("getWebSettings")["enabled"]
        secret = "desktop-test-credential-not-real"
        saved = service.invoke("saveWebSettings", {"provider": "tavily", "enabled": True, "apiKey": secret})
        assert saved["credentials"]["tavily"] and saved["readPages"]
        assert secret not in json.dumps(saved)
        with sqlite3.connect(service.store.path) as db:
            assert secret not in str(db.execute("SELECT value FROM documents").fetchall())
        if os.name == "nt":
            assert secret not in service.web.vault._path("desktop-web").read_text()
        service.invoke("saveWebSettings", {"provider": "tavily", "enabled": True, "apiKey": ""})
        assert service.web.environment({"search_provider": "tavily"}) == {"TAVILY_API_KEY": secret}
        previous = service.store.get("settings", "web")
        with pytest.raises(ValueError):
            service.invoke("saveWebSettings", {"provider": "searxng", "enabled": True, "readPages": False})
        assert service.store.get("settings", "web") == previous
        with pytest.raises(ValueError) as failure:
            service.invoke("saveWebSettings", {"provider": "tavily", "enabled": secret, "apiKey": secret})
        assert secret not in str(failure.value)
        saved = service.invoke("saveWebSettings", {"provider": "tavily", "enabled": False, "removeKey": True})
        assert not saved["enabled"] and not service.web.credentials().get("tavily")
        assert not service.store.get("settings", "web")
        with pytest.raises(ValueError, match="启用"):
            service.invoke("testWebTools")
    finally:
        service.close()


def test_searxng_real_search_reopen_and_failure(tmp_path, web_service):
    address, calls = web_service
    service = DesktopService(tmp_path)
    try:
        settings = {"provider": "searxng", "enabled": True, "readPages": False, "searxngUrl": address}
        assert service.invoke("saveWebSettings", settings)["enabled"]
        result = service.invoke("testWebTools")
        assert result["ok"] and result["tools"] == ["web_search"]
        assert calls[-1][0] == "/search" and calls[-1][1]["format"] == ["json"]
        assert service.web.environment({"search_provider": "searxng"}) == {"SEARXNG_URL": address}
        before = service.store.get("settings", "web")
        with pytest.raises(ValueError, match="仅支持搜索"):
            service.invoke("saveWebSettings", settings | {"readPages": True})
        with pytest.raises(ValueError):
            service.invoke("saveWebSettings", settings | {"searxngUrl": "https://user:secret@example.com"})
        assert service.store.get("settings", "web") == before
    finally:
        service.close()
    reopened = DesktopService(tmp_path)
    try:
        assert reopened.invoke("getWebSettings")["searxngUrl"] == address
        reopened.invoke("saveWebSettings", settings | {"searxngUrl": "http://127.0.0.1:1"})
        with pytest.raises(ToolError, match="request failed"):
            reopened.invoke("testWebTools")
    finally:
        reopened.close()
