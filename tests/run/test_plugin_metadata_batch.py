"""Verify real Git batch reads retain binary content and bound process count."""

import json
import subprocess
import sys

from tests.run.test_plugins import write_plugin
from vera.plugins.presentation import marketplace_presentations, package_presentation
from vera.plugins.source import Source


def test_oversized_artwork_keeps_the_plugin_description(tmp_path):
    root = write_plugin(tmp_path)
    value = json.loads((root / "plugin.json").read_text())
    value["interface"] = {"composerIcon": "./logo.png"}
    (root / "plugin.json").write_text(json.dumps(value))
    (root / "logo.png").write_bytes(b"z" * (256 * 1024 + 1))
    source = Source(str(root), root, None)
    files = set(source.files())
    expected = package_presentation(source, ".", files)
    assert expected["description"] == "Review changes." and "icon" not in expected
    assert marketplace_presentations(source, ["."], files)["."] == expected


def test_git_metadata_uses_constant_batches_and_preserves_binary_artwork(tmp_path):
    for number in range(12):
        root = write_plugin(tmp_path / f"plugins/kit-{number}", name=f"kit-{number}")
        value = json.loads((root / "plugin.json").read_text())
        value["interface"] = {"composerIcon": "./logo.svg"}
        (root / "plugin.json").write_text(json.dumps(value))
        (root / "logo.svg").write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg">\n</svg>\n')
    (tmp_path / "large.json").write_bytes(b"z" * (1024 * 1024 + 1))
    for arguments in [
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
    ]:
        subprocess.run(["git", "-C", str(tmp_path), *arguments], check=True, capture_output=True)
    commit = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    source = Source(str(tmp_path), tmp_path, commit)
    content = source.read_files(["plugins/kit-0/logo.svg", "large.json", "missing.json"])
    assert content == {"plugins/kit-0/logo.svg": (tmp_path / "plugins/kit-0/logo.svg").read_bytes()}
    script = r"""
import sys
from pathlib import Path
from vera.plugins.source import Source
from vera.plugins.presentation import marketplace_presentations
source = Source(sys.argv[1], Path(sys.argv[1]), sys.argv[2])
files = set(source.files())
calls = []
def audit(event, args):
    if event == "subprocess.Popen" and "cat-file" in args[1]:
        calls.append(args[1])
sys.addaudithook(audit)
rows = marketplace_presentations(source, [f"plugins/kit-{number}" for number in range(12)], files)
assert len(rows) == 12 and all(row["icon"].startswith("data:image/svg+xml;base64,") for row in rows.values())
assert len(calls) == 4, calls
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), commit], text=True, capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
