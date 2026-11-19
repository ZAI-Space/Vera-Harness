[English](contributing.md) · [简体中文](zh/contributing.md)

# Contributing

!!! abstract "Keep changes correct, readable, consistent and small"

    Read the relevant implementation, callers and tests before editing. Extend the existing Runtime and capability modules. Keep the Agent Loop independent of UI and optional services.

## Development setup

```bash
python -m pip install -e '.[full,channels]'
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python -m build
python -m mkdocs build --strict
python scripts/check_docs.py
```

Use actual files, subprocesses and explicit local protocol peers for new integration tests. Report unavailable backends and paid-provider scope separately. A passing skipped test is not validation of that backend.

## Branches and delivery

`dev` integrates daily work; `main` is for releases, hotfixes and production rollback. Create task branches from `dev`, named `<type>/-<kebab-case>`, and submit focused PRs to `dev`. Use conventional commits. Synchronize the target before merging and rerun affected checks. Squash daily work; release `dev` to `main` with a merge commit. Follow the current repository/user collaboration rules for branch protection and review.

## Documentation

Every public guide has English and Chinese versions. Preserve headings, admonitions, tables, runnable examples and API references. Update both language pages for behavior changes, retain exact config identifiers, and run the documentation checker plus strict build. Do not insert credentials or claim verification that did not run. [Documentation maintenance](documentation.md) lists the review map.
