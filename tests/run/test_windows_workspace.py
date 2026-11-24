"""Opt-in verification of the actual Windows desktop workspace namespace."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from vera.terminal.files import ProjectFiles


@pytest.mark.skipif(
    os.name != "nt" or not os.getenv("VERA_QA_DEFAULT_WORKSPACE"), reason="Requires the real Windows desktop workspace"
)
def test_workspace_file_can_be_listed_and_attached_through_windows_redirection():
    """Regression: MSIX redirects child files while the existing root resolves to its logical path."""
    root = Path(os.environ["VERA_QA_DEFAULT_WORKSPACE"])
    name = f"qa1122/read-{uuid4().hex}.txt"
    path = root / name
    path.parent.mkdir(exist_ok=True)
    path.write_text("VERA_NAMESPACE_READ_OK", encoding="utf-8")
    try:
        files = ProjectFiles(root)
        assert name in files.list("qa1122")
        assert "VERA_NAMESPACE_READ_OK" in files.attach("Read the selected file", [name])
    finally:
        path.unlink()
