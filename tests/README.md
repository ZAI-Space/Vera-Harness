# VERA tests

The test tree is organized by the boundary it verifies:

- `agents/`, `config/`, `environments/`, `models/`: focused unit and contract
  tests for the Python modules.
- `run/`: CLI, Runtime, channels, desktop service, markets, scheduler, storage
  and other integration tests.
- `utils/`: shared utility behavior.
- `test_data/`: small checked-in fixtures only.

Tests that need an optional backend declare the prerequisite and skip with an
explicit reason. A skip is not reported as a pass for that backend. Temporary
acceptance reports, screenshots, caches and model credentials stay outside the
repository.

Run the normal Python suite from the repository root:

```bash
python -m pytest -n 2 -ra
```

The real Electron acceptance suite lives with the desktop app and runs from
`desktop/` with `npm run test:ui`.
