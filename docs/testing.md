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

`src/vera/models/test_models.py` provides the deterministic model adapter used by the runtime.

## Python checks

From the root, with `.[full,channels]` installed:

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

Run `python -m pytest tests/run/test_examples.py -ra` to check the distributed examples. Integration tests use real files, subprocesses and local protocol services.

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

The UI runner covers settings, marketplaces, model configuration and assistant interactions in isolated scenarios. It starts Electron, a Python service and a local model protocol service, checks file and database changes, and prints the report directory. Set `VERA_PYTHON` to select an interpreter other than the root `.venv`. The global settings scenario starts the pinned Taskboard; prepare its installation as described in [Taskboard](taskboard.md).

## Test environments

- Run the default suite with `python -m pytest -n 2 -ra`. The `-ra` option displays a summary, including skipped cases.
- Container tests require the corresponding engine and image. Taskboard tests require its installed build.
- Use `--run-fire` to enable external model API tests. Configure provider credentials and a budget before running them.
- Run security reproduction cases in a separate isolated environment.

`main` is the only long-lived, default and production branch. Temporary task branches return through a squash PR after the required checks pass. Delete temporary branches after delivery and tag landed `main` commits for releases. See [contributing](contributing.md) for the workflow.
