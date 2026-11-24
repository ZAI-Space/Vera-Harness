[English](global_configuration.md) · [简体中文](../zh/advanced/global_configuration.md)

# Global configuration

!!! abstract "Environment and the private .env file"

    Startup prints the global config path. Environment variables take precedence over values loaded from that file. `VERA_GLOBAL_CONFIG_DIR` selects a different directory. Fresh settings use the VERA user config directory; when only the inherited directory exists, startup reuses it to preserve credentials, runs, skills and plugins. No existing data is moved or deleted.

```bash
vera-extra config setup
vera-extra config set VERA_MODEL_NAME openai/YOUR_MODEL
vera-extra config unset VERA_MODEL_NAME
vera-extra config edit
```

When setting a secret, omit the value and use the prompt instead of placing it in shell history. `$EDITOR` selects the editor; otherwise the command uses `nano`, which must exist on the host. A virtual environment activation controls which installed CLI is used.

## Model settings

| Variable | Purpose |
| --- | --- |
| `VERA_MODEL_NAME` | Default provider/model identifier |
| Provider-specific credential variables | Authentication for the selected adapter |
| `LITELLM_MODEL_REGISTRY_PATH` | Extra model-price registry JSON |
| `VERA_COST_TRACKING` | Accounting error behavior; ignoring errors is not a cost cap |
| `VERA_GLOBAL_CALL_LIMIT` / `VERA_GLOBAL_COST_LIMIT` | Process-wide call/cost accounting limits; zero disables |
| `VERA_MODEL_RETRY_STOP_AFTER_ATTEMPT` | Bounded provider retry attempts |

## Paths and startup

`VERA_COST_TRACKING` accepts `default`, `ignore_errors` and `tokens` in the LiteLLM, OpenRouter and Portkey adapters. `tokens` records reported usage without establishing a monetary cost. A zero compatibility cost does not mean that the provider request is free.

| Variable | Purpose |
| --- | --- |
| `VERA_CONFIG_DIR` | Extra configuration lookup directory |
| `VERA_CONFIG_PATH` | Default terminal YAML path |
| `VERA_INSPECTOR_STYLE_PATH` | Inspector stylesheet override |
| `VERA_BASH_PATH` | Explicit Git Bash executable on Windows |
| `VERA_SILENT_STARTUP` | Suppress the startup banner for machine-readable operations |
| `VERA_DEFAULT_RUN` | Python module for the compatible module launcher |

Operation-specific configuration belongs in [YAML overlays](yaml_configuration.md). Models, sandbox profiles, channels, MCP and scheduled jobs have distinct stores/config schemas. Do not put credentials in a public overlay or expose complete environment/config objects to the frontend.
