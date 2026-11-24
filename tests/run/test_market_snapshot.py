"""Check the bundled catalog as inert discovery data without starting services."""

import json
import re
from pathlib import Path


def test_bundled_docker_catalog_has_consistent_metadata_and_pinned_images():
    """Keep recommended entries resolvable and executable image identities immutable."""
    directory = Path(__file__).resolve().parents[2] / "src/vera/config/markets"
    snapshot = json.loads((directory / "docker.json").read_text(encoding="utf-8"))
    assert snapshot["source"] == "https://github.com/docker/mcp-registry"
    assert snapshot["endpoint"] == "https://desktop.docker.com/mcp/catalog/v3/catalog.yaml"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot["updatedAt"])
    registry = snapshot["registry"]
    assert isinstance(registry, dict) and registry
    recommendations = snapshot["recommended"]
    assert recommendations and len(recommendations) == len(set(recommendations))
    assert set(recommendations) <= registry.keys()
    for name, entry in registry.items():
        assert isinstance(name, str) and isinstance(entry, dict)
        for field in ["title", "description", "icon"]:
            assert isinstance(entry.get(field, ""), str)
        if image := entry.get("image"):
            assert re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image), name
    assert "MIT License" in (directory / "docker.LICENSE").read_text(encoding="utf-8")
