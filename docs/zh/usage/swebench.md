[English](../../usage/swebench.md) · [简体中文](swebench.md)

# SWE-bench

!!! abstract "推理和评分分开"

    swebench 批量生成预测，swebench-single 交互运行单题。仅跑推理不产生 benchmark 分数，需保留候选 SHA、模型参数、数据集版本/划分、题目清单和外部评测结果。

## 选择与执行

按 --help 使用 subset/split/slice/filter/shuffle/workers/model/config/output/redo 参数。自定义数据集需要现有 loader 能读取。先限制小批量、明确成本。Linux 镜像评测要求可运行后端；原生 Windows 本地成功不能替代容器测试。

已有 preds 决定跳过逻辑，仅删轨迹不会清除预测条目。中断可能已保存轨迹，必须检查状态/副作用后决定继续；失败与遗漏题仍在分母中。初始化长时间无响应时核对引擎、镜像拉取、资源和超时，不盲目重复启动。

## 初始化与评价

run.env_startup_command 使用实例变量渲染，运行可信初始化命令；Git 语法要真实有效。启动、模型、工具和评分错误分开记录。外部 evaluator 的版本和命令按其官方流程准备，不把上游公开得分当本候选效果。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
vera-extra swebench --help
vera-extra swebench --subset verified --split test --slice 0:5 --workers 1 -m openai/YOUR_MODEL -o ./results/pilot
vera-extra swebench-single --subset verified --split test --instance 0 -m openai/YOUR_MODEL
```
