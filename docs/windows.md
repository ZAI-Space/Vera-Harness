# Windows and Bash startup

Requires Python 3.10 or newer. Windows uses Git for Windows Bash; Linux uses its
existing shell environment. Git Bash is a command environment, not a Linux VM.

From PowerShell or CMD, in the checkout:

```powershell
.\start.cmd --help
.\start.cmd -m YOUR_PROVIDER/YOUR_MODEL
```

From Git Bash or Linux Bash:

```bash
bash scripts/start.sh --help
bash scripts/start.sh -m YOUR_PROVIDER/YOUR_MODEL
```

The first startup creates the checkout's `.venv` and installs this source tree.
Later starts reuse the environment. Python itself must already be installed.
Model selection and API keys still use the existing configuration setup.
Arguments and the caller's working directory are preserved. Windows uses
`.venv/Scripts/python.exe`; Linux uses `.venv/bin/python`.

## Git Bash discovery and installation

The Windows launcher checks `MSWEA_BASH_PATH`, the user cache, the Git installation
on PATH, the Git for Windows registry entries and standard installation paths.
It does not select `C:\Windows\System32\bash.exe`, which can launch WSL.

If Git Bash is missing, the launcher downloads full PortableGit from the official
Git for Windows GitHub release, verifies its published SHA256 digest, and extracts
it into `%LOCALAPPDATA%\mini-swe-agent\git`. Installation does not need administrator
privileges or change system PATH. Later starts work with the cached copy. Download
or verification failures stop startup with an error; an unverified archive is
never executed. Offline first-time setup requires manually installing Git for
Windows or copying a complete portable installation and setting `MSWEA_BASH_PATH`.

For a custom installation, in PowerShell:

```powershell
$env:MSWEA_BASH_PATH = 'D:\Tools\Git\bin\bash.exe'
.\start.cmd
```

Library users may set `LocalEnvironment(bash_path=...)`. Library construction never
downloads software. The repository launcher handles provisioning. An already
running Git Bash uses its installation directly; Linux never downloads PortableGit.

## Execution behavior

Windows actions explicitly invoke Bash with `--noprofile --norc -c`; starting Python
from Bash alone does not change Python's default Windows subprocess shell.
Commands keep the existing `{"command": "..."}` format, Bash tool name and completion
marker. Each action runs in a fresh shell. Existing Linux defaults are preserved.
Mintty sessions use Git's `winpty` console bridge when native Python cannot see a
Windows console. Redirected `--help` and noninteractive runs also work.

Paths passed to Windows tools can be converted by MSYS2. Prefer quoted paths with
forward slashes; use `cygpath` when an explicit Windows/POSIX conversion is needed.
The launcher does not globally disable MSYS2 path conversion. Windows timeouts
terminate the action's process tree with `taskkill /T /F` and bound output draining;
this is local command execution, not a sandbox. Linux-only container backends and
Linux benchmark images are outside the native Windows local-execution contract.

## Verification

```powershell
.venv\Scripts\python -m pytest tests/environments/test_local.py tests/environments/test_windows_local.py tests/agents/test_default.py tests/agents/test_interactive.py tests/config tests/test_init.py tests/run/test_windows_startup.py tests/utils -q
```

The startup tests use deterministic model responses and real Bash commands, with
no paid model calls. `.github/workflows/windows.yaml` covers Python 3.10 and 3.12.

Validation on 2026-11-17 used Windows x64, Python 3.12.13 and Git Bash 5.3.15:

- The command above passed 244 tests. One existing POSIX-only process-group test
  was skipped; the new Windows descendant-process regression passed.
- Environment/agent factory, trajectory-save and inspector checks passed another
  38 tests. Ruff lint/format and wheel/source builds passed.
- A fresh PortableGit download, SHA256 verification, extraction, cached reuse and
  `start.cmd --help` using that extracted copy were exercised in an isolated
  `.venv/portable-git-smoke` directory.
- An interactive Windows terminal reached `What do you want to do?` without a
  model request, and a visible Git Bash window was opened for inspection.
- Linux/WSL standard-library probes passed for execution, exit codes, partial
  timeout output and startup-script syntax. These were not a full Linux test run.

Python 3.10, ARM64 and hosted GitHub Actions were not part of that local validation.
No real model/API quality result is claimed by those checks. At that point the
repository had no remote, so checks ran directly. The repository now uses
`https://github.com/zml-mis/Vera-Harness.git`; pull requests targeting `dev` or
`main` run the complete Windows suite on Python 3.10 and 3.12.
