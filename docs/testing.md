[English](testing.md) · [简体中文](zh/testing.md)

# Testing and delivery

Use the existing test suites. Keep credentials and acceptance reports outside the repository.

## Maintained test locations

| Path | Coverage |
| --- | --- |
| `tests/agents`, `tests/models`, `tests/environments`, `tests/config`, `tests/utils` | Python component behavior and adapters. |
| `tests/run` | Runtime assembly, CLI, local protocols, workers, storage, channels, scheduler and integration fixtures. |
| `desktop/tests` | Frontend contracts, state, components and main/preload behavior; mirrors `desktop/src`. |
| `desktop/tests/ui` | Actual Electron acceptance and the shared launcher. |
| `tests/run/desktop_contract_trace.py` | Real Python events consumed by the TypeScript contract test. |

`src/vera/models/test_models.py` is a shipped deterministic model adapter, not a misplaced test suite.

## Python checks

From the root, with `.[full,channels]` installed:

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

Run `python -m pytest tests/run/test_examples.py -ra` to validate the distributed examples without a paid provider. New regression tests use real files and local protocol fixtures where practical. Do not replace missing integration evidence with mocks or remove failing tests.

## Desktop checks

From `desktop/`, after installing locked dependencies:

```bash
npm run check:boundary
npm run lint
npm run typecheck
npm test
npm run build
npm run test:ui
```

The UI runner executes five isolated scenarios for settings, global settings, marketplaces, model configuration and the general assistant. It starts Electron, a Python service and a local model protocol peer, checks actual file/database effects, and prints each evidence directory. Set `VERA_PYTHON` when the root `.venv` is not the intended interpreter. The global settings scenario starts the pinned optional Taskboard; prepare its installation first as described in [Taskboard](taskboard.md).

## Evidence limits

- Default pytest does not enable paid `--run-fire` tests.
- Missing containers, platforms, optional upstream applications or credentials can cause skips. Report each category.
- A local protocol peer validates integration, not model quality or live marketplace availability.
- Security reproduction requires its own isolated, bounded environment. Ordinary CI is engineering evidence.
- Verify the PR head SHA and every required CI job before merge; verify the resulting `main` SHA afterwards.

`main` is the only long-lived, default and production branch. Temporary task branches start at `main` and return through a squash PR; delete them after delivery. Tag landed `main` commits for releases. This repository uses a single-maintainer policy: PRs and all 10 required checks remain mandatory, with zero required human approvals. The maintainer can merge after checks pass; do not bypass branch protection or report unfinished checks as passing.
