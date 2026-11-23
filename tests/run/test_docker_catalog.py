"""Validate the shipped curated snapshot and local, non-executing transport plans."""

from vera.desktop.service import DesktopService
from vera.desktop.store import DesktopStore
from vera.markets.docker import DockerCatalog


def test_curated_catalog_has_publisher_artwork_descriptions_and_pinned_transports(tmp_path):
    catalog = DockerCatalog(DesktopStore(tmp_path))
    rows = catalog.search()["entries"]
    assert rows[0]["name"] == "playwright"
    assert {row["name"] for row in rows} >= {"github-official", "context7", "brave", "mongodb"}
    assert all(row["description"] and row["icon"] and row["repository"].startswith("https://") for row in rows)
    playwright = catalog.preview("playwright")
    assert "@sha256:" in playwright["config"]["args"][-1]
    assert playwright["config"]["command"] == "docker" and not playwright["required_inputs"]
    github = catalog.preview("github-official")
    assert github["config"]["env_from"] == ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    context = catalog.preview("context7")
    assert context["config"]["headers_from"] == {"CONTEXT7_API_KEY": "CONTEXT7_API_KEY"}
    assert catalog.search("playwright")["entries"][0]["title"] == "Playwright"
    assert catalog.search("浏览器")["entries"][0]["name"] == "playwright"
    assert all(row["descriptionZh"] for row in rows)
    assert not catalog.search("no-such-service-47687")["entries"]


def test_market_registration_preserves_digest_and_rejects_duplicates_or_stale_preview(tmp_path):
    import pytest

    service = DesktopService(tmp_path)
    try:
        plan = service.invoke("inspectMcpMarket", {"identifier": "playwright"})
        with pytest.raises(ValueError, match="已更新"):
            service.invoke("addMcpMarket", {"identifier": "playwright", "version": "stale"})
        service.invoke("addMcpMarket", {"identifier": "playwright", "version": plan["version"]})
        row = service.invoke("mcpConfigList")["global"][0]
        assert row["config"] == plan["config"] and not row["enabled"]
        with pytest.raises(ValueError, match="already uses"):
            service.invoke("addMcpMarket", {"identifier": "playwright"})
    finally:
        service.close()
