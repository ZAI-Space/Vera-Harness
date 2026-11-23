[English](documentation.md) · [简体中文](zh/documentation.md)

# Documentation maintenance

Write for users, integrators and maintainers. Organize pages by the reader's task. Keep historical acceptance reports out of product documentation.

## Page ownership

- README: purpose, requirements, first successful use and documentation links.
- Quickstart and feature pages: complete steps, input, result, recovery and permission boundaries.
- Architecture and API pages: ownership, data flow, contracts, state and errors.
- API reference: existing Python symbols instead of copied signatures.
- Testing and contribution pages: commands, directories, prerequisites and evidence limits.

## Changes

Maintain English paths and matching `zh/` pages together, including language links. Preserve exact commands, identifiers, fields and versions. Read implementation, callers and tests before describing behavior. Use one topic per paragraph and clear actions in procedures. Remove obsolete claims and unsupported completion statements.

Document public entry points, interfaces and important state changes briefly. Python uses English docstrings; frontend comments follow the module's existing Chinese convention. Preserve third-party license text unchanged.

Keep reports and screenshots outside the repository. Product pages contain repeatable operations, explicit limits and maintenance links. Update paired pages and `mkdocs.yml` after behavior changes. See [testing and delivery](testing.md).

## Checks

```bash
python scripts/check_docs.py
python -m mkdocs build --strict
```

Static checks validate links, language pairs and API references. Also read the README, installation path and built pages. These checks do not establish live-model, optional-service or production-security acceptance.
