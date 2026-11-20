"""Find Git Bash, or provision official PortableGit when run as the Windows launcher.

This module uses only the standard library so the launcher works before project
dependencies are installed. Library callers only discover Bash; downloads happen
at the explicit repository startup entry point.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def git_cache_dir() -> Path:
    """Return the per-user PortableGit directory without modifying system PATH."""
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    current, legacy = base / "VERA" / "git", base / "mini-swe-agent" / "git"
    return legacy if legacy.is_dir() and not current.exists() else current


def find_git_bash(bash_path: str = "") -> str | None:
    """Find Git Bash, never the System32 WSL launcher; reject invalid explicit paths."""
    if explicit_path := bash_path or os.environ.get("VERA_BASH_PATH") or os.environ.get("MSWEA_BASH_PATH"):
        if not Path(explicit_path).is_file():
            raise FileNotFoundError(f"Git Bash executable does not exist: {explicit_path}")
        return str(Path(explicit_path).resolve())
    roots = [git_cache_dir()]
    if git_executable := shutil.which("git"):
        roots.extend(Path(git_executable).resolve().parents[:3])
    if os.name == "nt":
        import winreg

        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\GitForWindows") as key:
                    roots.append(Path(winreg.QueryValueEx(key, "InstallPath")[0]))
            except FileNotFoundError:
                continue
    for variable, suffix in (("ProgramFiles", "Git"), ("LOCALAPPDATA", "Programs/Git")):
        if directory := os.environ.get(variable):
            roots.append(Path(directory) / suffix)
    return next((str(root / "bin" / "bash.exe") for root in roots if (root / "bin" / "bash.exe").is_file()), None)


def install_git_bash(cache_dir: Path | None = None) -> str:
    """Download, verify and extract official PortableGit into a user-owned cache.

    Requires internet access on the first run. Failed downloads are discarded;
    cached installs are reused. No administrator privileges or PATH edits are used.
    """
    cache_dir = cache_dir or git_cache_dir()
    executable = cache_dir / "bin" / "bash.exe"
    if executable.is_file():
        return str(executable)
    architecture = {"amd64": "64-bit", "x86_64": "64-bit", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower()
    )
    if architecture is None:
        raise RuntimeError("Automatic Git Bash setup requires x64 or ARM64 Windows. Install Git for Windows manually.")
    request = urllib.request.Request(
        "https://api.github.com/repos/git-for-windows/git/releases/latest",
        headers={"User-Agent": "VERA-windows-setup", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset = next(
        asset
        for asset in release["assets"]
        if asset["name"].startswith("PortableGit-") and asset["name"].endswith(f"-{architecture}.7z.exe")
    )
    digest = asset.get("digest") or ""
    if not digest.startswith("sha256:"):
        raise RuntimeError("Official PortableGit release has no SHA256 digest; install Git for Windows manually.")
    url = asset["browser_download_url"]
    if not url.startswith("https://github.com/git-for-windows/git/releases/download/"):
        raise RuntimeError("Unexpected PortableGit download URL.")
    print(f"Git Bash not found. Downloading {asset['name']} from Git for Windows...", flush=True)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="git-setup-", dir=cache_dir.parent) as temporary_dir:
        archive = Path(temporary_dir) / asset["name"]
        with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest.removeprefix("sha256:"):
            raise RuntimeError("PortableGit SHA256 verification failed; the download was not executed.")
        extracted = Path(temporary_dir) / "git"
        subprocess.run(
            [str(archive), "-y", f"-o{extracted}"],
            check=True,
            timeout=120,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if not (extracted / "bin" / "bash.exe").is_file():
            raise RuntimeError("PortableGit extraction did not produce bin/bash.exe.")
        if cache_dir.exists():
            raise RuntimeError(f"Incomplete Git cache exists at {cache_dir}; move it aside and retry.")
        extracted.rename(cache_dir)
    return str(executable)


def main() -> int:
    """Bootstrap Git Bash and forward all arguments to the common startup script."""
    bash_path = find_git_bash() or install_git_bash()
    environment = os.environ | {
        "VERA_BASH_PATH": bash_path,
        "VERA_BOOTSTRAP_PYTHON": Path(sys.executable).as_posix(),
    }
    return subprocess.call(
        [
            bash_path,
            "--noprofile",
            "--norc",
            str(Path(__file__).resolve().parents[3] / "scripts" / "start.sh"),
            *sys.argv[1:],
        ],
        env=environment,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, StopIteration, KeyError, subprocess.SubprocessError) as error:
        print(
            f"Windows startup failed: {error}\nInstall Git for Windows or set VERA_BASH_PATH and retry.",
            file=sys.stderr,
        )
        sys.exit(1)
