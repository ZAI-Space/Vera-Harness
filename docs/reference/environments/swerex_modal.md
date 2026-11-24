[English](swerex_modal.md) · [简体中文](../../zh/reference/environments/swerex_modal.md)

# SWE-ReX Modal

!!! note "SWE-ReX Modal Environment class"

    - [Read on GitHub](https://github.com/ZAI-Space/Vera-Harness/blob/main/src/vera/environments/extra/swerex_modal.py)
    - Requires [Modal](https://modal.com) account and authentication

This environment executes commands in [Modal](https://modal.com) sandboxes using [SWE-ReX](https://github.com/swe-agent/swe-rex).

## Setup

1. Install the full dependencies:
   ```bash
   python -m pip install -e '.[full]'
   ```

2. Set up Modal authentication:
   ```bash
   modal setup
   ```

## Usage

Evaluate GPT-5 mini on SWE-bench using Modal:
```
vera-extra swebench \
    --config src/vera/config/benchmarks/swebench_modal.yaml \
    --subset verified \
    --split test \
    --workers 1 \
    -o ./results/gpt5-mini-modal
```

{% include-markdown "../../_footer.md" %}
