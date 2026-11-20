"""Real Windows/Git Bash regressions: paths, native tools and process-tree timeout."""

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from vera.environments.local import LocalEnvironment

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows process and path contracts")


def test_unicode_paths_and_native_python(tmp_path):
    working_dir = tmp_path / "中文 workspace"
    working_dir.mkdir()
    python_path = shlex.quote(Path(sys.executable).as_posix())
    result = LocalEnvironment(cwd=str(working_dir)).execute(
        {
            "command": f"echo '中文内容' > '文件 name.txt'; {python_path} -c \"from pathlib import Path; print(Path('文件 name.txt').read_text(encoding='utf-8'))\""
        }
    )
    assert result["returncode"] == 0
    assert "中文内容" in result["output"]
    assert (working_dir / "文件 name.txt").read_text(encoding="utf-8") == "中文内容\n"


def test_timeout_kills_native_descendants_and_preserves_output(tmp_path):
    pid_file = tmp_path / "descendants.txt"
    script = tmp_path / "children.py"
    script.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "Path(sys.argv[1]).write_text(f'{os.getpid()}\\n{child.pid}')\n"
        "print('before-timeout', flush=True)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    started = time.monotonic()
    result = LocalEnvironment(timeout=2).execute(
        {"command": " ".join(shlex.quote(path.as_posix()) for path in (Path(sys.executable), script, pid_file))}
    )
    elapsed = time.monotonic() - started
    process_ids = pid_file.read_text().splitlines()
    try:
        assert result["extra"]["exception_type"] == "TimeoutExpired"
        assert result["returncode"] == -1
        assert "before-timeout" in result["output"]
        assert elapsed < 10
        for process_id in process_ids:
            status = subprocess.run(
                ["tasklist.exe", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert f'"{process_id}"' not in status.stdout
    finally:
        for process_id in process_ids:
            subprocess.run(["taskkill.exe", "/PID", process_id, "/T", "/F"], capture_output=True, timeout=5)
