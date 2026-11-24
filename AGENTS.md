# VERA development guide

Keep code correct, readable, consistent and concise.

## Read before editing

Read the implementation, its callers and relevant tests. Reuse existing code when
its behavior matches the task. Choose the simplest design and limit changes to the
requested responsibility. Preserve other public behavior.

## Project map

- `src/vera/agents`: the Agent Loop and conversation control.
- `src/vera/runtime.py`: shared Runtime composition.
- `src/vera/environments` and `src/vera/models`: execution and model adapters.
- `src/vera/desktop`: authenticated desktop services and worker integration.
- `src/vera/channels`, `src/vera/scheduler`: messaging and background execution.
- `src/vera/plugins`, `src/vera/tools`: optional capabilities and tool policies.
- `desktop/src`: Electron main, preload, contracts and React renderer.
- `tests` and `desktop/tests`: maintained tests and fixtures.
- `examples`: runnable examples. `docs` and `docs/zh`: paired public guides.

Keep UI and optional services outside the core Agent Loop. See
`docs/architecture.md`, `docs/testing.md` and `docs/contributing.md` for details.

## Names and style

- Support Python 3.10 and later. Use type annotations and modern built-in types.
- Python uses `snake_case` for functions, variables and files; `PascalCase` for
  classes; and `UPPER_SNAKE_CASE` for constants.
- TypeScript uses `camelCase` for functions and variables, `PascalCase` for types
  and component files, and `UPPER_SNAKE_CASE` for constants. Other files follow the
  existing `kebab-case` convention. Hooks use `useXxx`.
- Use meaningful names. Follow framework and public API conventions first.
- Let Ruff and Biome determine formatting and lint rules. Prefer `pathlib` for
  ordinary paths. Use bounded streaming reads when file size or trust requires it.
- Give each function one responsibility. Review nesting beyond three levels.
  Extract repeated logic only when it represents the same rule.
- Review files approaching 1000 lines. Limit growth in larger files and explain
  necessary additions.

## Comments and errors

Document module entry points, public interfaces and critical workflows. Explain
parameters, results, preconditions, boundaries, errors and state changes where
callers need them. Keep comment language consistent and update comments with code.
Delete obsolete comments and disabled code.

Catch errors at a boundary that can recover, clean up or present a useful failure.
Do not silently discard unexpected failures or expose credentials in error text.
Keep temporary values when their names make a condition or data flow clearer.

## Tests and local checks

Use pytest for Python and the existing Vitest and Electron acceptance suites for
the desktop. Put maintained tests and fixtures in `tests/` or `desktop/tests/`.
The runtime adapter `src/vera/models/test_models.py` is an intentional exception.
Test behavior, boundaries and failure paths. Use real files and local protocol
peers for integration checks. Follow the existing Ruff parametrization rules.

Before committing, format changed code, run lint and affected tests. Run:

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
cd desktop
npm run lint
npm run typecheck
npm test
npm run build
npm run test:ui
```

Use `docs/testing.md` for environment requirements and documentation checks.
Record unavailable dependencies, skipped integrations and paid-model validation
separately. Do not remove tests or weaken assertions to make CI pass.

## Git delivery

Create daily branches from `dev`, named `<type>/-<kebab-case>`, and open a focused
PR back to `dev`. Keep daily diffs below 400 lines when practical. Use
`<type>(<scope>): <subject>` commits, with an imperative subject of at most 50
characters and no final period. Types are `feat`, `fix`, `docs`, `style`,
`refactor`, `perf`, `test`, `build`, `ci` and `chore`. Keep one intent per commit.

Reference daily issues with `Refs #123`. Use `Closes #123` for issues completed by
a release or hotfix. Keep development PRs in Draft, review the diff before Ready,
synchronize the target branch and rerun affected checks before merging.

`main` is for releases, hotfixes and production rollback. Squash daily and hotfix
PRs. Release `dev` to `main` with a merge commit; synchronize hotfixes back through
a `main` to `dev` PR. Delete merged task branches. Revert through a PR.

The owner has selected a single-maintainer policy: PRs and required CI checks
remain mandatory, with zero required human approvals. Keep branch protection and
required checks. AI review is evidence, not a human GitHub approval.

## Repository hygiene

Do not commit credentials or sensitive configuration. Keep temporary reports and
local acceptance output outside the repository. Preserve required upstream
licenses, notices and compatibility identifiers. Change generated files through
their source and generator, third-party code through upgrades or existing patches,
and lockfiles through the package manager. Every change must have a task,
verification or necessary generated-output reason.
