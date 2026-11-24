"""Refresh the bundled Docker catalog and recommended publisher icons.

Run with the project Python interpreter. The existing snapshot supplies the
reviewed recommendation order; the Docker feed supplies all runtime metadata.
This updates catalog data only and never pulls images or executes servers.
"""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from vera.desktop.store import DesktopStore
from vera.markets.docker import SNAPSHOT, DockerCatalog


def main():
    """Regenerate the checked-in snapshot through the production fetch/validation path."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        from pathlib import Path

        catalog = DockerCatalog(DesktopStore(Path(directory)))
        catalog.refresh()
        value = catalog.data

    def cache_icon(name):
        row = value["registry"].get(name)
        if not row:
            return
        address = row.get("icon", "")
        url = urlsplit(address)
        if url.scheme != "https" or url.hostname not in {"avatars.githubusercontent.com", "www.docker.com"}:
            return
        response = requests.get(address, timeout=15, allow_redirects=False)
        response.raise_for_status()
        if len(response.content) > 65536 or not response.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("Publisher icon exceeded size/type constraints.")
        row["iconData"] = (
            "data:"
            + response.headers["Content-Type"].split(";")[0]
            + ";base64,"
            + base64.b64encode(response.content).decode()
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(cache_icon, value["recommended"]))
    value["updatedAt"] = datetime.now(timezone.utc).date().isoformat()
    SNAPSHOT.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Updated {len(value['registry'])} Docker MCP entries.")


if __name__ == "__main__":
    main()
