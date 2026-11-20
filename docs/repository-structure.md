[English](repository-structure.md) · [简体中文](zh/repository-structure.md)

# Repository structure

VERA uses a small monorepo layout with one Python package and one desktop
application. Source, tests, examples, documentation and generated output have
separate ownership.

| Path | Ownership | What belongs here |
| --- | --- | --- |
| `src/vera/` | Python source | Runtime, agents, models, tools, memory, channels and CLI modules |
| `desktop/` | Desktop source | Electron main process, preload, renderer, contracts and desktop tests |
| `tests/` | Python verification | Unit, integration and system tests plus small fixtures |
| `examples/` | Public demonstrations | Safe plugin, Skill, MCP and configuration examples |
| `docs/` | Product documentation | English/Chinese tutorials, how-to guides, reference and architecture explanations |
| `scripts/` | Maintainer tools | Portable startup, documentation, boundary and verification scripts |
| `.github/` | Repository automation | CI workflows, issue forms and pull-request templates |
| `site/`, `dist/`, `.venv/`, `node_modules/`, `desktop/out/` | Generated/local | Never commit; recreate from the lockfiles and build commands |

Root files are limited to project entry points and repository policy: README
editions, license and notices, package metadata, Git configuration, startup
entry points and contributor/agent instructions. A feature guide belongs in
`docs/`; an executable public example belongs in `examples/`; a verification
fixture belongs in `tests/`.

The repository does not keep phase plans, temporary acceptance reports,
screenshots, local logs or copied build output. Durable verification procedures
belong in tests and durable facts about the product belong in the paired
documentation pages.
