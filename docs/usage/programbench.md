[English](programbench.md) · [简体中文](../zh/usage/programbench.md)

# ProgramBench

!!! abstract "Generate programs and evaluate them separately"

    The ProgramBench runner uses its own dataset and environment setup. Install its dataset, evaluator dependencies and execution backend before running tasks.

```bash
vera-extra programbench --help
```

Select the dataset, split/slice, model, worker count, configuration and output directory with the current command's options. Start with a small task set, save the instance list and generated programs, then run the external evaluator for that dataset version.

Before reusing an output directory, review its existing records and choose the tasks to continue or rerun.

::: vera.run.benchmarks.programbench
