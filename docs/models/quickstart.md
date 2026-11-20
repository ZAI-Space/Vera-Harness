[English](quickstart.md) · [简体中文](../zh/models/quickstart.md)

# Model configuration

!!! abstract "Choose the adapter and the provider"

    `model_class` chooses VERA's adapter; `model_name` identifies the provider model. The default adapter is LiteLLM. Named tools, MCP, planning and goals require native tool calling. Available provider models and prices belong to the provider; a frozen model list is not authoritative.

## Credentials and model selection

```bash
vera-extra config setup
vera-extra config set VERA_MODEL_NAME openai/YOUR_MODEL
vera -m openai/YOUR_MODEL
```

Set the appropriate credential in the environment or through the interactive setup: for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `PORTKEY_API_KEY` or `REQUESTY_API_KEY`. Do not commit keys or place real secrets in shared examples.

## YAML overlays

```yaml
model:
  model_class: litellm
  model_name: openai/YOUR_MODEL
  model_kwargs:
    max_tokens: 4096
    timeout: 60
```

```bash
vera -c vera.yaml -c model.yaml
```

Passing `-c` replaces the implicit default list, so include `vera.yaml` before an overlay. Only use parameters supported by the selected provider. Anthropic-family model names receive the existing cache-control configuration when it was not explicitly set.

| Adapter | Interface | Native tools |
| --- | --- | --- |
| `litellm` | Chat Completions through LiteLLM | Yes |
| `litellm_response` | Responses through LiteLLM | Yes |
| `openrouter`, `openrouter_response` | OpenRouter | Yes |
| `portkey`, `portkey_response` | Portkey gateway | Yes |
| `requesty` | Requesty gateway | Yes |
| `litellm_textbased`, `openrouter_textbased` | Text actions | Bash only |
| `deterministic` | Predefined outputs | Test fixture, no provider calls |

`litellm_response` is the supported shortcut, not the old `litellm_response_toolcall` example. A custom adapter may be supplied by full Python class path. Each tool registry needs its own model adapter instance. See the [model reference](../reference/models/overview.md).

## Local and compatible endpoints

```yaml
model:
  model_class: litellm
  model_name: openai/local-model
  model_kwargs:
    api_base: http://127.0.0.1:8000/v1
```

Endpoint-specific authentication and actual tool support must be verified. Configure cost metadata for unrecognized models; do not treat disabling accounting errors as a spending limit. See [local models](local_models.md) and [troubleshooting](troubleshooting.md).
