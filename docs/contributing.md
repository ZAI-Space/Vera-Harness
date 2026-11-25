[English](contributing.md) · [简体中文](zh/contributing.md)

# Contributing

!!! abstract "Keep changes correct, readable, consistent and small"

    Read the relevant implementation, callers and tests before editing. Extend the existing Runtime and capability modules. Keep the Agent Loop independent of UI and optional services.

## Development setup

```bash
python -m pip install -e '.[full,channels]' build twine
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python -m build
python -m mkdocs build --strict
python scripts/check_docs.py
```

Use real files, subprocesses and local protocol services for integration tests. See [testing](testing.md) for environment setup and commands.

## Branches and delivery

`main` is the only long-lived, default and production branch. Create temporary task branches from `main`, named `<type>/-<kebab-case>`, and submit focused PRs to `main`. Use conventional commits. Synchronize the target before merging and rerun affected checks. Squash daily and hotfix PRs. Tag the landed `main` commit for a release and delete temporary branches after delivery.

Keep `main` protected. The single-maintainer policy requires PRs and all 10 required CI checks, with zero required human approvals.

## Documentation

Every public guide has English and Chinese versions. Preserve headings, admonitions, tables, runnable examples and API references. Update both language pages for behavior changes, retain exact config identifiers, and run the documentation checker plus strict build. Use placeholders for credentials in examples. See [documentation maintenance](documentation.md).
