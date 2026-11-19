<div align="center">
  <img src="docs/assets/vera-logo.png" alt="VERA Logo" width="200" />
  <h1>VERA</h1>
  <p><strong>Compose agent capabilities around a task, from terminal to desktop.</strong></p>
  <p>Models · Tools · Memory · Delegation · Isolation · Standing goals</p>
  <p>
    <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square" />
    <img alt="Windows and Linux" src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-008C95?style=flat-square" />
    <a href="LICENSE.md"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-6F42C1?style=flat-square" /></a>
  </p>
  <p><a href="README.md">简体中文</a> · <strong>English</strong></p>
  <p><a href="docs/quickstart.md">Quick start</a> · <a href="docs/index.md">Documentation</a> · <a href="docs/frontend-integration.md">Frontend integration</a> · <a href="https://github.com/zml-mis/Vera-Harness/issues">Issues</a></p>
</div>

---

VERA is a modular agent harness. Terminal, channel and scheduled tasks share a Python Runtime that assembles models, tools, memory, Subagents and execution environments. State observation and outer controllers extend the system around its small Agent Loop.

## Capabilities

| Task need | VERA provides |
| --- | --- |
| Understand a project | `@` project-file search/attachments and on-demand Skills |
| Act and research | Bash, web search/extraction, MCP and a shared tool registry |
| Delegate by role | Configurable Subagent models, tools, skills, instructions and budgets |
| Remember across sessions | Hindsight project/shared banks and bounded context projection |
| Extend workflows | GitHub/Gitee plugins, MCP Registry and skills.sh |
| Control execution | `confirm` / `yolo` / `human`, user-configured Docker/Bubblewrap sandboxes |
| Keep working | Planning-only `/plan`, bounded `/goal`, independent scheduled tasks |
| Inspect and recover | Lifecycle events, SQLite receipts, trajectories and reconciled resumption |
| Connect remotely | Weixin QR login and Feishu application-bot long connections |
| Improve versioned source | External evaluation/evolution with candidates separate from production branches |

## Get started

Python 3.10+ is required. Windows local execution uses Git Bash; Linux uses Bash. Install from this source repository:

```bash
git clone --branch dev https://github.com/zml-mis/Vera-Harness.git
cd Vera-Harness
python -m venv .venv
```

Activate with `.\.venv\Scripts\Activate.ps1` in PowerShell, `source .venv/Scripts/activate` in Git Bash, or `source .venv/bin/activate` on Linux. Then:

```bash
python -m pip install -e '.[mcp,channels]'
vera-extra config setup
vera
```

Repository launchers are `.\start.cmd` in PowerShell/CMD and `bash scripts/start.sh` in Git Bash/Linux. They prepare the checkout environment; Windows can provision verified PortableGit when Bash is absent. Sandbox engines and images remain user-managed. Real tasks need model configuration and credentials; help commands do not.

## In the terminal

```text
Inspect @src/main.py and report actual verification results
/skill
/mcp
/subagent
/sandbox
/plan Design regression coverage for this project
/goal Implement the tests and verify the relevant checks pass
/goal status
```

Tab selects candidates; Esc then Enter submits multiline input. Permissions, run modes and sandboxes are separate: `human` means manual command input, `yolo` skips per-action approval, `/plan` does not implement, and `/goal` does not grant extra authority. Local execution remains available without an installed sandbox.

## Documentation and integration

- [English documentation](docs/index.md) / [中文文档](docs/zh/index.md), with paired page links.
- [Frontend integration](docs/frontend-integration.md): sessions, state, selections, approval and storage boundaries. Python APIs exist; a desktop transport and real UI acceptance still require implementation.
- [Naming migration](docs/advanced/v2_migration.md): preferred `vera`, `VERA_*` and `vera.yaml` names, with explicit historical settings compatibility.
- [Documentation maintenance](docs/documentation.md): per-page review map and stale-content corrections.

## Develop and verify

```bash
python -m pip install -e '.[full,channels]'
python -m ruff check src tests
python -m ruff format --check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

Daily branches start from `dev` and merge through PRs into `dev`; releases enter `main`. Report optional prerequisites, paid provider tests and human platform acceptance separately. Skipped tests and upstream scores are not VERA results.

## License and provenance

Distributed under [MIT](LICENSE.md). [Third-party notices](THIRD_PARTY_NOTICES.md) retain source attribution and required copyright notices separately from product branding.
