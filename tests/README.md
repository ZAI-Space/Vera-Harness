# VERA tests

The test tree is organized by the boundary it verifies:

- `agents/`, `config/`, `environments/`, `models/`: focused Python component tests.
- `run/`: Runtime, CLI, channels, desktop, markets, scheduler and storage integration.
- `utils/`: shared utility behavior.
- `test_data/`: small maintained fixtures.
- `../desktop/tests/`: frontend contracts, stores, components and Electron acceptance.

Run `python -m pytest -n 2 -ra` from the repository root. Run `npm run test:ui`
from `desktop/` after building and preparing the optional Taskboard dependency.
See [testing](../docs/testing.md) for the complete checks and prerequisites.

Tests declare optional prerequisites and skip with an explicit reason. A skip
does not establish acceptance. Keep temporary reports, screenshots, caches and
model credentials outside the repository.
