"""Regression checks for transient consoles when the real backend has a GUI parent."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Win32 console allocation requires Windows")
def test_gui_parent_keeps_backend_commands_headless_and_reaps_jobs(tmp_path):
    """Check console handles, failure propagation, cancellation, timeout and Git results."""
    gui_python = Path(sys._base_executable).with_name("pythonw.exe")
    assert gui_python.is_file()
    repository = Path(__file__).resolve().parents[2]
    site_packages = Path(sys.prefix) / "Lib/site-packages"
    fixture = Path(__file__).with_name("windows_console_fixture.py")
    bootstrap = (
        "import runpy,site,sys;site.addsitedir(sys.argv.pop(1));"
        "script=sys.argv.pop(1);sys.argv[0]=script;runpy.run_path(script,run_name='__main__')"
    )
    environment = os.environ | {
        "VERA_SILENT_STARTUP": "1",
        "PYTHONUTF8": "1",
        "PYTHONPATH": os.pathsep.join([str(repository / "src"), str(repository)]),
        "VERA_GLOBAL_CONFIG_DIR": str(tmp_path / "user-config"),
        "VERA_TEST_CONSOLE_PYTHON": sys.executable,
    }
    with (tmp_path / "output.log").open("wb") as output:
        child = subprocess.run(
            [str(gui_python), "-c", bootstrap, str(site_packages), str(fixture), str(tmp_path)],
            env=environment,
            cwd=repository,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    assert child.returncode == 0, (tmp_path / "output.log").read_text(encoding="utf-8")
    result = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert result["parent"] == {"allocated": False, "visible": False}
    for index in range(3):
        assert result[f"probe{index}"] == {"allocated": False, "visible": False}
    assert result["job"] == {"status": "returned", "allocated": False, "visible": False}
    assert result["failed"] == {"status": "returned", "returncode": 7}
    assert result["timeout"] == {"status": "timeout", "childReaped": True}
    assert result["cancelled"] == {"status": "cancelled", "childReaped": True}
    assert result["git"] == result["pluginGit"] == result["branch"] == "console-test"
    assert result["branches"]["current"] == "console-test"
    assert result["files"] == ["example.py"]
