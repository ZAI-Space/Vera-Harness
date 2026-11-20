[English](v2_migration.md) · [简体中文](../zh/advanced/v2_migration.md)

# Compatibility and migration

!!! abstract "VERA identity, compatible runtime interfaces"

    The distribution is now `vera-harness`; preferred commands are `vera`, `vera-extra` and `python -m vera`. Install this checkout rather than fetching the unrelated upstream package. Product version and trajectory schema version are different identifiers.

```bash
python -m pip install -e '.[mcp,channels]'
vera --help
vera-extra --help
```

## Existing integrations

| Interface | Current behavior |
| --- | --- |
| `vera`, `vera-extra`, `python -m vera` | Preferred entry points |
| `mini`, `mini-swe-agent`, `mini-extra`, `mini-e` | Installed command aliases to the current VERA CLI |
| `vera.*` | Current namespace; update old `minisweagent.*` Python imports and custom class paths |
| `vera.yaml`, `vera_textbased.yaml` | Current built-in files; old short built-in names are accepted as lookup aliases |
| `VERA_*`, `VERA_CONFIG_PATH` | Current variables; inherited `MSWEA_*` values are read when a new key is absent |
| `vera_version`, `trajectory_format: vera-1.1` | New serialized names; historic trajectory structures remain readable by the Inspector |
| Saved run database | History remains queryable; known legacy package prefixes are normalized for resume, while execution configuration and receipt checks remain enforced |

Fresh settings use the VERA user config directory. An existing inherited directory is reused when no new directory exists; an explicit VERA_GLOBAL_CONFIG_DIR takes precedence. The original Git cache can likewise be reused. No user data is moved/deleted automatically. A changed execution configuration or unknown custom class can still prevent resume; renaming is not permission to bypass reconciliation. For frontend deployments, assign explicit store locations and unique chat session IDs.

## Older text-action adapters

Native tool calling is the normal path. `litellm_textbased` and `openrouter_textbased` remain available for Bash-only text actions. The completion marker is `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`. Flow exceptions live in `vera.exceptions`; `Agent.run()` returns exit metadata. Model adapters parse actions and format observations; configuration uses Pydantic.

```python
from vera.exceptions import FormatError, Submitted
```

Do not use removed `--config-class` examples or the old `litellm_response_toolcall` shortcut. Use full component import paths, `-c` config overlays and the supported `litellm_response` model shortcut. The old visual `-v` terminal and dedicated issue runner are not restored by VERA.

## Desktop preparation

Use typed Python state/session APIs rather than user-visible labels or serialized field renaming. See [frontend integration](../frontend-integration.md). Legal upstream attribution remains in the repository license and third-party notices; it is separate from product branding.
