"""Exercise discovered local Bash runtimes rather than a static frontend shell list."""

import os

import pytest

from vera.desktop.shells import command_shells, shell_command
from vera.environments.local import LocalEnvironment


@pytest.mark.skipif(os.name != "nt", reason="Windows executable and WSL discovery")
def test_detected_windows_shells_execute_in_the_selected_workspace(tmp_path):
    """A selected WSL/Git Bash runtime must execute and retain the real project directory."""
    rows = command_shells(refresh=True)
    assert rows[0]["id"] == "system"
    for row in rows[1:]:
        command = shell_command(row["id"])
        result = LocalEnvironment(cwd=str(tmp_path), shell_command=command).execute(
            {"command": "printf VERA_SHELL_VERIFIED > shell-proof.txt; cat shell-proof.txt; uname -s"}
        )
        assert result["returncode"] == 0, result
        assert result["output"].startswith("VERA_SHELL_VERIFIED")
        assert (tmp_path / "shell-proof.txt").read_text() == "VERA_SHELL_VERIFIED"
    with pytest.raises(ValueError, match="不可用"):
        shell_command("wsl:vera-unavailable-distribution")
