[English](inspector.md) · [简体中文](../zh/usage/inspector.md)

# Inspector: browse agent trajectories

!!! abstract "Inspect local artifacts"

    The Textual inspector reads `.traj.json` files; it does not replay tool calls or require a model. It can display sensitive project text, so keep artifacts private. See [output formats](output_files.md).

```bash
vera-extra inspector
vera-extra inspector /path/to/run.traj.json
vera-extra inspector /path/to/results
```

## Key bindings

| Key | Action |
| --- | --- |
| `q` | Quit |
| `h` / Left, `l` / Right | Previous/next step |
| `j` / Down, `k` / Up | Scroll |
| `H`, `L` | Previous/next trajectory |
| `e` | Open current step with optional jless |

Hold Alt/Option while selecting text when the terminal needs that override. The inspector groups messages by step and can show reasoning already present in a private trajectory; that is distinct from a frontend or channel deliberately exposing internal reasoning.

::: vera.run.utilities.inspector
