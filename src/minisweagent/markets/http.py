"""Read bounded JSON catalogs without following redirects or executing returned content."""

import json
from urllib.parse import urlsplit

import requests

from minisweagent.tools import ToolError


def catalog_json(url: str, *, params: dict | None = None) -> dict:
    """Fetch at most 2 MiB; HTTPS or a local test peer is required. Failures raise ToolError."""
    address = urlsplit(url)
    if (
        address.username
        or address.password
        or address.fragment
        or not (
            address.scheme == "https"
            or address.scheme == "http"
            and address.hostname in {"127.0.0.1", "localhost", "::1"}
        )
    ):
        raise ToolError("Catalog endpoints require credential-free HTTPS.")
    try:
        with requests.get(url, params=params, stream=True, timeout=(5, 20), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ToolError(f"Catalog request failed (HTTP {response.status_code}).")
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise ToolError("Catalog response exceeds 2 MiB.")
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ToolError("Catalog response must be a JSON object.")
            return result
    except (requests.RequestException, json.JSONDecodeError) as error:
        raise ToolError(f"Catalog unavailable or returned invalid JSON ({type(error).__name__}).") from None
