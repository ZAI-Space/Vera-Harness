[English](programbench.md) · [简体中文](../zh/usage/programbench.md)

# ProgramBench

!!! abstract "Generate programs and evaluate them separately"

    The ProgramBench runner uses its own dataset and environment setup. It requires optional ProgramBench/evaluator prerequisites and a working execution backend. The presence of a CLI command does not establish that those resources are installed.

```bash
vera-extra programbench --help
```

Select the dataset, split/slice, model, worker count, config overlays and output directory with the current command's options. Start with a bounded task set and retain the full selection manifest. Generated artifacts/predictions and external evaluator scores are separate evidence. Do not apply upstream marketing or score claims to VERA.

Use the existing per-instance setup/patch collection contract and the external project's evaluator instructions for the chosen dataset version. Keep backend startup failures, model failures, unscored outputs and skipped prerequisites visible. Reusing an output directory requires reviewing existing records before deciding to redo work.

::: vera.run.benchmarks.programbench
