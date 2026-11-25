[English](faq.md) · [简体中文](zh/faq.md)

# FAQ

!!! question "Does VERA work on Windows and Linux?"

    Yes. Native Windows local execution uses Git for Windows Bash; Linux uses its configured shell. Git Bash is not a Linux VM. Docker, Bubblewrap and other optional environments have separate requirements. See [startup](windows.md) and [sandbox selection](sandbox.md).

??? question "Do I need Docker?"

    No. Local execution is available with the current user's host permissions. Sandboxes are opt-in and user-configured. An explicitly requested unavailable sandbox fails instead of silently using the host. VERA does not automatically install sandbox engines or images.

??? question "Is VERA limited to Bash tools?"

    No. Bash remains the basic file/build interface, alongside registered web tools, MCP services, Skills, plugins and Subagents. Tool-calling model adapters are required for named capabilities. Text-action models retain their Bash path.

??? question "What is the difference between permissions, plan/goal and sandbox?"

    Permissions control approval (`confirm`, `yolo`, `human`). `/plan` restricts the task to inspection and a saved plan. `/goal` continues a standing objective within a budget. A sandbox controls the command environment. Selecting any one does not implicitly select the others.

??? question "Where are settings stored?"

    Startup prints the global `.env` path. `VERA_GLOBAL_CONFIG_DIR` overrides it. The inherited directory and variable names are retained for compatibility. Environment variables take precedence when the file is loaded. See [global configuration](advanced/global_configuration.md).

??? question "Why does a later command forget cd or export?"

    <a id="why-no-shell-session"></a>
    Each Bash action uses a fresh shell. Prefix the working directory or environment in the command, or configure `environment.cwd` and `environment.env`. The project filesystem can persist; a shell session does not.

??? question "Can a goal or scheduler run forever?"

    No. Goals have turn, cost and elapsed budgets. Jobs have per-invocation limits. Accounting happens at call/boundary checks, so an in-flight provider request can overshoot the remaining allowance. A scheduler needs a live service and does not wake a powered-off machine.

??? question "How does the desktop connect to the backend?"

    The Electron desktop uses an authenticated loopback Python service for sessions, streaming events and Runtime operations. See [frontend integration](frontend-integration.md) for startup and configuration.
