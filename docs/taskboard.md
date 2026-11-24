[English](taskboard.md) · [简体中文](zh/taskboard.md)

# Taskboard integration

VERA can open a separately installed dashi-taskboard and run a selected task through a desktop conversation. The upstream application is optional and is not bundled.

## Install and open

On Windows, read and run `scripts/setup-taskboard.ps1` from the repository root. It checks out revision `bc25451c5c49a14abb6c4e8250b62c626b007f8a`, installs/builds the upstream app, retains its licenses and records the installation under the VERA profile. The script needs Git, Node, npm and network access. It does not run upstream Codex injection/install scripts.

Open the taskboard page in the desktop to start the owned service. If installation or Node is absent, the page reports that prerequisite. `VERA_TASKBOARD_HOME` can select an existing built installation; that override makes its source the owner's responsibility.

## Run a task

Select the project, model and permission policy before execution. The adapter checks task identity/version and current state, then creates a dedicated desktop execution conversation. Follow streaming output and respond to approvals in that conversation.

A completed run becomes ready for review. It does not automatically accept the task. Stop running execution conversations before stopping the taskboard service. Closing the owned service preserves task data in the desktop profile.

## Service boundary

The adapter supplies `127.0.0.1`, a random instance token, a separate secret and a private data directory. The board is displayed in a sandboxed iframe. Its capability URL must remain private. Upstream route enforcement belongs to the separately installed revision; VERA's local `/invoke` authentication is a different boundary.

See `tests/run/test_taskboard_integration.py` and `test_taskboard_execution.py`. An absent upstream installation is an explicit skip, not proof of integration acceptance.
