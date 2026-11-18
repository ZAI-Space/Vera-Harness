"""Hindsight REST adapter for one configured project memory bank."""

import ipaddress
import os
import re
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests

MAX_RECALL_CHARS = 4000


class HindsightError(RuntimeError):
    """Hindsight configuration, transport or response error."""


class HindsightMemory:
    """Recall relevant facts and retain curated notes using the Hindsight v1 API."""

    def __init__(self, base_url: str, bank_id: str, *, api_key: str = ""):
        """Bind requests to a single bank; do not connect until recall or retain."""
        self.bank_id = bank_id.strip()
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.bank_id):
            raise HindsightError(
                "Set HINDSIGHT_BANK_ID to a bank ID containing letters, digits, underscores or hyphens."
            )
        url = urlsplit(base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.query or url.fragment:
            raise HindsightError(
                "HINDSIGHT_BASE_URL must be an HTTP(S) base URL without credentials, query or fragment."
            )
        if api_key and url.scheme == "http" and not _is_loopback(url.hostname):
            raise HindsightError("Use HTTPS when sending a Hindsight API key to a non-loopback server.")
        self._url = f"{base_url.rstrip('/')}/v1/default/banks/{self.bank_id}"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    @classmethod
    def from_env(cls, bank_id: str | None = None) -> "HindsightMemory":
        """Read the endpoint, bank and optional credential from the current process."""
        api_key = os.getenv("HINDSIGHT_API_KEY", "")
        if key_file := os.getenv("HINDSIGHT_API_KEY_FILE"):
            try:
                api_key = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError) as error:
                raise HindsightError("Could not read HINDSIGHT_API_KEY_FILE.") from error
        return cls(
            os.getenv("HINDSIGHT_BASE_URL", "http://127.0.0.1:8888"),
            bank_id if bank_id is not None else os.getenv("HINDSIGHT_BANK_ID", ""),
            api_key=api_key,
        )

    def _request(self, method: str, operation: str, suffix: str, body: dict, *, read_timeout: int) -> dict:
        try:
            response = requests.request(
                method,
                self._url + suffix,
                json=body,
                headers=self._headers,
                timeout=(3, read_timeout),
                allow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                raise HindsightError(f"Hindsight {operation} returned HTTP {response.status_code}.")
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            raise HindsightError(f"Hindsight {operation} failed ({type(error).__name__}).") from error
        if not isinstance(result, dict):
            raise HindsightError(f"Hindsight {operation} returned an invalid JSON object.")
        return result

    def recall(self, query: str) -> list[str]:
        """Return text from observation-preferred recall for existing callers."""
        return [record["text"] for record in self.recall_records(query)]

    def recall_records(self, query: str, *, prefer_observations: bool = True) -> list[dict]:
        """Keep Hindsight's fact IDs, types, dates and provenance alongside text."""
        if not query.strip():
            return []
        result = self._request(
            "POST",
            "recall",
            "/memories/recall",
            {
                "query": query[:MAX_RECALL_CHARS],
                "budget": "low",
                "max_tokens": 800,
                "types": ["world", "experience", "observation"] if prefer_observations else ["world", "experience"],
                "prefer_observations": prefer_observations,
                "include": {"entities": None},
            },
            read_timeout=5,
        )
        if not isinstance(results := result.get("results"), list):
            raise HindsightError("Hindsight recall response is missing its results list.")
        return [item for item in results if isinstance(item, dict) and isinstance(item.get("text"), str)]

    def reflect(self, query: str) -> dict:
        """Ask Hindsight to synthesize relevant memories with supporting facts."""
        result = self._request(
            "POST",
            "reflect",
            "/reflect",
            {"query": query[:MAX_RECALL_CHARS], "budget": "low", "max_tokens": 800, "include": {"facts": {}}},
            read_timeout=30,
        )
        if not isinstance(result.get("text"), str):
            raise HindsightError("Hindsight reflect response is missing its text.")
        return result

    def retain(self, note: str, *, context: str = "", document_id: str = "", tags: tuple[str, ...] = ()) -> None:
        """Store an explicit note synchronously in this bank, raising if Hindsight rejects it."""
        note = note.strip()
        if not note:
            raise HindsightError("Provide a nonempty project note.")
        item = {"content": note}
        if context:
            item["context"] = context
        if document_id:
            item["document_id"] = document_id
        if tags:
            item["tags"] = list(tags)
        result = self._request("POST", "retain", "/memories", {"items": [item], "async": False}, read_timeout=60)
        if result.get("success") is not True:
            raise HindsightError("Hindsight did not confirm the memory write.")

    def set_validity(self, memory_id: str, *, is_valid: bool, reason: str = "") -> None:
        """Restore or invalidate a fact by its Hindsight ID; invalidation requires a reason."""
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", memory_id):
            raise HindsightError("Provide a valid Hindsight fact ID.")
        body = {"state": "valid" if is_valid else "invalidated"}
        if not is_valid:
            if not reason.strip():
                raise HindsightError("Provide a reason for invalidating the fact.")
            body["reason"] = reason.strip()
        self._request("PATCH", "update memory", f"/memories/{quote(memory_id, safe='')}", body, read_timeout=30)


def _is_loopback(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
