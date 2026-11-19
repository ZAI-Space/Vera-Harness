[English](quickstart.md) · [简体中文](zh/quickstart.md)

# Quick start

!!! abstract "Requirements"

    Python 3.10 or newer, Git for cloning, and Bash for local command execution. Windows uses Git for Windows Bash. A model and its provider credentials are required for real tasks; `--help` does not query a model.

## Install from source

```bash
git clone --branch dev https://github.com/zml-mis/Vera-Harness.git
cd Vera-Harness
python -m venv .venv
```

=== "PowerShell"

    ```powershell
    .\.venv\Scripts\Activate.ps1
    python -m pip install -e '.[mcp,channels]'
    vera --help
    ```

=== "Git Bash"

    ```bash
    source .venv/Scripts/activate
    python -m pip install -e '.[mcp,channels]'
    vera --help
    ```

=== "Linux Bash"

    ```bash
    source .venv/bin/activate
    python -m pip install -e '.[mcp,channels]'
    vera --help
    ```

The documented install source is this repository. The package name alone is not a claim that a public PyPI release has been published. For a minimal install use `pip install -e .`; development adds `.[dev]` or `.[full,channels]`.

## Configure a model

```bash
vera-extra config setup
vera
```

The interactive setup asks for a model identifier and, optionally, the provider's key. Prefer the hidden/prompted input or a process environment variable to secrets in command arguments. Check the provider's model identifier and account permissions. [Model configuration](models/quickstart.md) describes adapter-specific options.

## Submit a task

```text
Explain @src/main.py
/skill
/mcp
/plan Add a regression test for this module
/goal Fix the failing tests and show the verification output
```

Use Tab to complete and Esc then Enter to submit multiline input. `confirm` asks before operations, `yolo` runs without per-action approval, and `human` executes user-entered commands. A permission mode does not create a sandbox.

## Repository launchers

PowerShell/CMD: `.\start.cmd`. Git Bash/Linux: `bash scripts/start.sh`. These bootstrap the checkout's virtual environment. The Windows launcher can provision verified PortableGit if Bash is absent; sandbox engines remain user-managed. See [Windows startup](windows.md).

```bash
vera-extra --help
python -m vera --help
```

Use `vera`, `vera-extra` and `python -m vera` for new integrations. Legacy `mini` and `mini-extra` commands remain aliases; old Python imports must change to `vera.*`. Existing configuration and stored runs are reused when applicable; see the [migration guide](advanced/v2_migration.md).
