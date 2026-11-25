[English](repository-structure.md) · [简体中文](zh/repository-structure.md)

# Repository structure

This repository contains the VERA Runtime, terminal and desktop adapters, tests, examples and user documentation. Keep each file in the directory that owns its behavior.

| Path | Contents | Commit policy |
| --- | --- | --- |
| `src/vera/` | Python Runtime, models, agents, tools, environments, storage, channels and adapters | Commit source and maintained package data. |
| `desktop/src/` | Electron main process, preload bridge, contracts and React renderer | Commit source; maintained tests belong in `desktop/tests/`. Keep the renderer independent from the Python Agent SDK. |
| `tests/` | Python unit, integration and local protocol tests | Put maintained tests here. Use `tests/run/` for cross-module and process tests. |
| `desktop/tests/` | Frontend unit and component tests | Mirror the tested source paths; UI acceptance lives in `desktop/tests/ui/`. |
| `examples/` | Safe plugin and configuration examples | Use placeholder credentials and local paths. Do not call paid services. |
| `docs/` and `docs/zh/` | Paired English and Chinese documentation | Update both pages when behavior changes. Preserve exact commands and identifiers. |
| `mkdocs.website.yml` and `scripts/build_website_docs.py` | Documentation integration for an external landing page | Export to an existing directory outside this repository. See [website documentation](website.md). |
| `desktop/third_party/` and `THIRD_PARTY_NOTICES.md` | Source and license notices | Keep notices with redistributed source. |
| `scripts/` | Repository maintenance and launch scripts | Do not store credentials or reports in the repository. |

## Generated and local files

Do not commit `.venv/`, Python caches, coverage output, `desktop/node_modules/`, `desktop/out/`, `desktop/.local/`, `desktop/coverage/`, `site/`, local trajectories, logs, reports or credentials. The UI acceptance command writes screenshots and logs to a temporary directory; keep those artifacts outside the repository.

Promotional landing page source is maintained outside this repository. Exported website documentation also stays in that external directory.

## Naming and ownership

Use `snake_case` for Python modules and functions, `PascalCase` for React components, and the existing `camelCase` convention for TypeScript functions and stores. Name a file for one topic. Split a file when it approaches 1,000 lines or combines unrelated responsibilities.

Use English for Python API names and public technical documentation. Preserve Chinese UI comments and bilingual documentation where they are part of the product surface. Comments must describe current behavior and must not preserve disabled code.

## Checks before delivery

Run the relevant checks from the repository root:

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

Run the desktop checks from `desktop/`:

```bash
npm run check:boundary
npm run lint
npm run typecheck
npm test
npm run build
npm run test:ui
```

See [testing](testing.md) for test environments and commands.
