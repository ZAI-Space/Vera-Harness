[English](litellm_response.md) · [简体中文](../../zh/reference/models/litellm_response.md)

# Litellm Response Model

!!! note "LiteLLM Response API Model class"

    - [Read on GitHub](https://github.com/zml-mis/Vera-Harness/blob/dev/src/vera/models/litellm_response_model.py)

    ??? note "Full source code"

        ```python
        --8<-- "src/vera/models/litellm_response_model.py"
        ```

!!! tip "When to use this model"

    * Use this model class when you want to use OpenAI's [Responses API](https://platform.openai.com/docs/api-reference/responses) with native tool calling.
    * This is particularly useful for models like GPT-5 that benefit from the extended thinking/reasoning capabilities provided by the Responses API.
    * The adapter flattens recorded response output into stateless API input on each query; it does not require provider-side previous_response_id state.

## Usage

To use the Response API model, specify `model_class: "litellm_response"` in your agent config:

```yaml
model:
  model_class: "litellm_response"
  model_name: "openai/gpt-5.2"
  model_kwargs:
    drop_params: true
    reasoning:
      effort: "high"
```

Or via command line:

```bash
vera -m "openai/gpt-5.2" --model-class litellm_response
```

::: vera.models.litellm_response_model

{% include-markdown "../../_footer.md" %}
