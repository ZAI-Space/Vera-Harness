[English](local_models.md) · [简体中文](../zh/models/local_models.md)

# Local models

!!! abstract "Endpoint and accounting are separate"

    A local OpenAI-compatible server needs the right base URL, provider identifier and actual model/tool support. It also needs cost metadata if the adapter cannot derive usage prices. Local hosting does not imply a zero-cost model.

## Configure an endpoint

```yaml
model:
  model_class: litellm
  model_name: openai/local-model
  model_kwargs:
    api_base: http://127.0.0.1:8000/v1
```

```bash
vera -c vera.yaml -c local-model.yaml
```

Use the endpoint's required credentials through environment variables. Named capabilities need native tool calling; if only text actions work, choose a text-action adapter and accept its Bash-only capability scope. The VERA process, not the shell sandbox, sends model requests.

## Register costs

```json
{
  "openai/local-model": {
    "input_cost_per_token": 0.0,
    "output_cost_per_token": 0.0,
    "max_tokens": 8192,
    "litellm_provider": "openai",
    "mode": "chat"
  }
}
```

This zero-price entry is only appropriate when the operator has established those actual accounting prices. Point `model.litellm_model_registry` or `LITELLM_MODEL_REGISTRY_PATH` at the JSON file. Check provider usage fields and pricing units against actual requests. `cost_tracking: ignore_errors` suppresses missing-price errors; it is not a spending control and can make reported cost incomplete.

For Portkey, `litellm_model_name_override` can map a gateway name to the provider's pricing identifier. Supported settings come from the adapter's current Config class in the [reference](../reference/models/overview.md). Model server installation, hardware sizing and provider pricing are outside this repository's CLI bootstrap.
