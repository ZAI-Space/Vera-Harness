[English](overview.md) · [简体中文](../../zh/reference/models/overview.md)

# Models Overview

This page provides an overview of all available model classes in VERA.

## Model Classes

| Class | Shortcut | Endpoint | Toolcalls | Description |
|-------|----------|----------|-----------|-------------|
| [`LitellmModel`](litellm.md) | `litellm` | `/chat/completions` | ✅ | Default model using [LiteLLM](https://docs.litellm.ai/docs/providers) for broad provider support (OpenAI, Anthropic, 100+ providers) |
| [`LitellmTextbasedModel`](litellm.md) | `litellm_textbased` | `/chat/completions` | ❌ | LiteLLM with text-based actions (no native tool calling) |
| [`LitellmResponseModel`](litellm_response.md) | `litellm_response` | `/responses` | ✅ | LiteLLM with [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) and native tool calling |
| [`OpenRouterModel`](openrouter.md) | `openrouter` | `/chat/completions` | ✅ | [OpenRouter](https://openrouter.ai/) API integration |
| [`OpenRouterTextbasedModel`](openrouter.md) | `openrouter_textbased` | `/chat/completions` | ❌ | OpenRouter with text-based actions |
| [`OpenRouterResponseModel`](openrouter.md) | `openrouter_response` | `/responses` | ✅ | OpenRouter Responses API with native tool calling |
| [`PortkeyModel`](portkey.md) | `portkey` | `/chat/completions` | ✅ | [Portkey](https://portkey.ai/) AI gateway integration |
| [`PortkeyResponseAPIModel`](portkey_response.md) | `portkey_response` | `/responses` | ✅ | Portkey with Responses API support |
| [`RequestyModel`](requesty.md) | `requesty` | `/chat/completions` | ✅ | [Requesty](https://requesty.ai/) API integration |
| [`DeterministicModel`](test_models.md) | `deterministic` | N/A | ❌ | Returns predefined outputs (for testing) |
| [`RouletteModel`](extra.md) | — | Meta | ❌ | Randomly selects from multiple models |
| [`InterleavingModel`](extra.md) | — | Meta | ❌ | Alternates between models in sequence |

{% include-markdown "../../_footer.md" %}
