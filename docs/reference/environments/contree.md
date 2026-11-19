[English](contree.md) · [简体中文](../../zh/reference/environments/contree.md)

# ConTree

!!! note "ConTree Environment class"

    - [Read on GitHub](https://github.com/zml-mis/Vera-Harness/blob/dev/src/vera/environments/extra/contree.py)
    - Requires [ConTree](https://contree.dev) token

    ??? note "Full source code"

        ```python
        --8<-- "src/vera/environments/extra/contree.py"
        ```

::: vera.environments.extra.contree

This environment executes commands in [ConTree](https://contree.dev) sandboxes using [ConTree SDK](https://github.com/nebius/contree-sdk)

## Setup

1. Install the dependencies:
   ```bash
   python -m pip install -e '.[contree]'
   ```

2. Set up ConTree token and base_url:
   ```bash
   export CONTREE_TOKEN="your-contree-token"
   export CONTREE_BASE_URL="your-given-base-url-for-contree"
   ```

## Usage

Run VERA like with any other environment:
```
vera-extra swebench \
    --subset verified \
    --split test \
    --workers 1 \
    --environment-class contree
```

It can be specified both through cli parameter or by setting `environment_class` to `contree` in your swebench.yaml config

{% include-markdown "../../_footer.md" %}
