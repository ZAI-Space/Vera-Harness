# VERA examples

Run examples from the repository root after installing the project.

## Offline Runtime

```bash
vera -c examples/basic.yaml -t "Complete the offline demonstration" -o offline-example.traj.json --exit-immediately
```

The deterministic adapter returns one fixed completion. It makes no provider request and runs no tool. The trajectory is local output; do not commit it.

## Plugin declarations

- `plugins/review-kit/`: a local Skill and a budgeted reviewer role. The role has Bash authority; its instructions are not a security sandbox.
- `plugins/github/`: the official GitHub MCP endpoint. Actual execution requires network access and a scoped `GITHUB_TOKEN` environment variable.

Installing a plugin leaves it disabled. Inspect its declarations before enabling it. These examples contain no live credentials.

`tests/run/test_examples.py` loads both manifests and runs the offline configuration without connecting to the remote MCP service.
