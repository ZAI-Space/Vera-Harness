"""Lossless, session-scoped deduplication of inline image payloads in desktop storage."""

import base64
from hashlib import sha256

MARKER = "__vera_image_blob_v1__"


def image_digests(value) -> set[str]:
    """Retain every stored image reference when pruning one session's blobs."""
    if isinstance(value, list):
        return set().union(*(image_digests(item) for item in value))
    if not isinstance(value, dict):
        return set()
    result = {value[MARKER]} if isinstance(value.get(MARKER), str) else set()
    for item in value.values():
        result.update(image_digests(item))
    return result


def encode_images(value, blobs: dict[str, bytes]):
    """Replace only typed image payloads; text and model/tool arguments stay unchanged."""
    if isinstance(value, list):
        return [encode_images(item, blobs) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for name, item in value.items():
        prefix = ""
        encoded = None
        if name == "data" and str(value.get("mimeType", "")).startswith("image/") and isinstance(item, str):
            encoded = item
        elif name == "url" and isinstance(item, str) and item.startswith("data:image/") and ";base64," in item:
            prefix, encoded = item.split(",", 1)
            prefix += ","
        if encoded is not None:
            try:
                content = base64.b64decode(encoded, validate=True)
            except ValueError:
                result[name] = item
                continue
            digest = sha256(content).hexdigest()
            blobs[digest] = content
            result[name] = {MARKER: digest, "prefix": prefix}
        else:
            result[name] = encode_images(item, blobs)
    return result


def decode_images(value, owner: str, db):
    """Resolve references only within their owning session; missing media fails visibly."""
    if isinstance(value, list):
        return [decode_images(item, owner, db) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for name, item in value.items():
        is_image_field = (name == "data" and str(value.get("mimeType", "")).startswith("image/")) or name == "url"
        if is_image_field and isinstance(item, dict) and MARKER in item:
            if (
                set(item) != {MARKER, "prefix"}
                or not isinstance(item[MARKER], str)
                or not isinstance(item["prefix"], str)
            ):
                raise ValueError("会话图片引用格式无效，请从截图整理备份恢复。")
            row = db.execute(
                "SELECT content FROM image_blobs WHERE owner=? AND digest=?", (owner, item[MARKER])
            ).fetchone()
            if row is None:
                raise ValueError("会话图片缺失，请从截图整理备份恢复。")
            result[name] = item["prefix"] + base64.b64encode(row[0]).decode("ascii")
        else:
            result[name] = decode_images(item, owner, db)
    return result
