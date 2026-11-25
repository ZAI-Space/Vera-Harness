[English](swebench.md) · [简体中文](../zh/usage/swebench.md)

# SWE-bench

!!! abstract "Inference and evaluation are separate"

    `vera-extra swebench` generates predictions for a batch; `swebench-single` runs an instance interactively. Running inference alone does not produce a benchmark score. Record model settings, dataset split, selected instance IDs, candidate SHA and external evaluation results.

```bash
vera-extra swebench --help
vera-extra swebench --subset verified --split test --slice 0:5 --workers 1 -m openai/YOUR_MODEL -o ./results/pilot
vera-extra swebench-single --subset verified --split test --instance 0 -m openai/YOUR_MODEL
```

Use a functioning backend appropriate to the benchmark images; native Windows local execution is not equivalent to Linux benchmark-image execution. Backend startup may pull images according to its own config. Inspect `docker info` and available space/memory if initialization stalls. Alternative backends need actual installed runtimes and compatible images.

## Selection and continuation

The CLI supports dataset/subset, split, slice, instance regex, shuffling, workers, model, overlays, output directory and redo controls. `--subset` can name a dataset loadable by the existing dataset loader. Check current `--help` for types/defaults. Existing predictions drive completion skipping; deleting only a trajectory does not clear the corresponding prediction entry.

Inspect every selected task, including failed/aborted tasks, before a continuation. Preserve logs, trajectories, prediction files and the exact instance manifest. A removed or failed task must not silently leave the evaluation denominator. Trajectories can be saved during execution/finally handling; do not assume interruption leaves no artifact. Unknown effects require inspection rather than blind replay.

## Environment setup and scoring

`run.env_startup_command` is rendered with instance variables and executes before the Agent. Supply only trusted setup commands and valid Git syntax. Container cache, installation, startup and model runtime failures need separate diagnostics.

Submit the generated predictions to the external SWE-bench evaluator. Follow its documentation for the selected dataset version and scoring command.

## Implementation

::: vera.run.benchmarks.swebench
