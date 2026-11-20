"""Store login credentials privately: Windows DPAPI or owner-only Unix files."""

import base64
import ctypes
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from vera.channels.config import ChannelError


def _protect(value: bytes, *, decrypt: bool = False) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("value", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    operation = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ChannelError("Windows could not protect/unprotect these credentials for the current user.")
    try:
        return ctypes.string_at(target.value, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.value, ctypes.c_void_p))


def private_directory(path: Path) -> Path:
    """Create owner-only state on Unix; Windows inherits the user's directory ACL."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
    return path


class CredentialStore:
    """Persist named Weixin account credentials atomically without logging their values."""

    def __init__(self, directory: Path):
        self.directory = directory / "credentials"

    def _path(self, account: str) -> Path:
        from hashlib import sha256

        return self.directory / f"{sha256(account.encode()).hexdigest()}.json"

    def save(self, account: str, credentials: dict) -> None:
        """Replace one login; DPAPI binds Windows tokens to the current Windows user."""
        private_directory(self.directory)
        value = json.dumps(credentials).encode()
        if os.name == "nt":
            value = json.dumps({"dpapi": base64.b64encode(_protect(value)).decode()}).encode()
        with NamedTemporaryFile(dir=self.directory, delete=False) as temporary:
            temporary.write(value)
            temporary.flush()
            os.fsync(temporary.fileno())
            name = Path(temporary.name)
        try:
            if os.name != "nt":
                name.chmod(0o600)
            os.replace(name, self._path(account))
        finally:
            name.unlink(missing_ok=True)

    def load(self, account: str) -> dict:
        """Return one decrypted login, or fail without including sensitive stored data."""
        try:
            value = self._path(account).read_bytes()
            data = json.loads(value)
            if "dpapi" in data:
                data = json.loads(_protect(base64.b64decode(data["dpapi"]), decrypt=True))
            if not isinstance(data, dict):
                raise ValueError("Expected an object")
            return data
        except (OSError, ValueError, KeyError):
            raise ChannelError(f"No usable login for account {account!r}; run channels login first.") from None

    def delete(self, account: str) -> None:
        """Remove local credentials; this does not revoke the provider-side binding."""
        self._path(account).unlink(missing_ok=True)

    def has(self, account: str) -> bool:
        """Check for a stored account without decrypting it or treating corrupt data as absent."""
        return self._path(account).is_file()
