# VERA examples

This directory contains small, inspectable examples that can be copied into a
local VERA configuration. They are demonstrations of public manifests and
capability declarations, not production plugins and not test doubles for the
runtime.

## Contents

- `plugins/review-kit/` demonstrates a Skill and a Subagent declaration.
- `plugins/github/` demonstrates a plugin with an MCP service declaration.

Examples must remain safe to inspect without credentials or network access.
They may contain placeholders, but must not contain tokens, private paths or
generated test output. Runtime fixtures belong under `tests/`, not here.
