"""Verify worker imports, project cwd and arguments with actual Python children."""

import json
import os
import subprocess
import sys

import pytest

from vera.utils.python_process import python_module_command


@pytest.mark.parametrize("safe_path", [False, True])
def test_module_command_ignores_implicit_project_imports(tmp_path, safe_path):
    """A same-named project package must not replace the trusted worker package."""
    workspace = tmp_path / "project with spaces"
    workspace.mkdir()
    trusted = tmp_path / "trusted source"
    package = trusted / "worker_fixture"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "main.py").write_text(
        "import json, os, sys\nprint(json.dumps({'origin':'trusted','cwd':os.getcwd(),'arguments':sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    shadow = workspace / "worker_fixture"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise RuntimeError('Project package was imported')\n", encoding="utf-8")
    environment = os.environ | {"PYTHONPATH": str(trusted), "PYTHONDONTWRITEBYTECODE": "1"}
    environment.pop("PYTHONSAFEPATH", None)
    if safe_path:
        environment["PYTHONSAFEPATH"] = "1"
    arguments = ["-", "value with spaces", "--literal"]
    result = subprocess.run(
        python_module_command("worker_fixture.main", *arguments),
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "origin": "trusted",
        "cwd": str(workspace),
        "arguments": arguments,
    }
    assert not result.stderr
    assert python_module_command("worker_fixture.main")[0] == sys.executable
