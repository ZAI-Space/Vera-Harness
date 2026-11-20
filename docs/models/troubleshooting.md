[English](troubleshooting.md) · [简体中文](../zh/models/troubleshooting.md)

# Model troubleshooting

!!! abstract "Preserve the actual provider error"

    Check the adapter, provider/model name, credential variable and endpoint before changing agent code. Do not attribute an unnamed authentication error to a different service or include secret values in an issue.

## Authentication

A 401 or authentication exception usually needs a valid credential for the selected provider, account access to the model, or the correct API endpoint. With LiteLLM, include the provider prefix, such as `openai/YOUR_MODEL`. A missing prefix can select an unintended provider and produce unrelated credential errors.

```bash
vera-extra config setup
vera-extra config edit
```

The editor displays private settings: do not share its contents unredacted. Process environment values may override the file; restarting a daemon is necessary after its inherited environment changes.

## Missing prices and usage

Unknown model prices stop normal accounting. Register the model as described in [local models](local_models.md). Portkey can use `litellm_model_name_override` to map its gateway model name to a LiteLLM pricing name. Ignoring errors may underreport cost; it does not make model requests free.

## Unsupported parameters or tool calls

Provider models differ in support for temperature, reasoning fields, tool schemas and token limits. Remove unsupported `model_kwargs` and check the actual provider contract. VERA does not maintain a fixed list of model-specific parameter rules. Named capabilities require a native tool-calling adapter; text-only adapters cannot advertise MCP, web, plan or goal tools.

## Network, limits and invalid output

Inspect the provider's status/error type, timeout and retry policy. A format error records the response and any charged cost; repeated malformed responses can stop the run. Steps, elapsed time and cost are checked at boundaries; an in-flight request may continue after cancellation. Save the run ID, redacted configuration and exact candidate version when reporting a problem.
