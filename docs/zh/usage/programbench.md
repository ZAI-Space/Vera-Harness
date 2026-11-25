[English](../../usage/programbench.md) · [简体中文](programbench.md)

# ProgramBench

ProgramBench 使用独立数据集、实例初始化和程序评测流程。运行前需安装数据集、评测器依赖和对应执行后端。

按 `--help` 选择数据集、划分、切片、模型、worker、配置和输出目录。先运行小批量任务，保存实例清单与生成程序，再使用对应版本的外部评测器评分。重用输出目录前，核查已有记录并选择继续或重跑的任务。

## 配置、命令与源码示例

```bash
vera-extra programbench --help
```

## API 参考

::: vera.run.benchmarks.programbench
