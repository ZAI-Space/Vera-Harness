[English](../evolution.md) · [简体中文](evolution.md)

# 版本化源码演化

!!! abstract "外部实验控制器"

    历史 VERA Runtime 编辑下一代源码，可信控制器运行固定检查和评测，接受的候选成为后续优化器/基线。不会自动改开发工作区、安装包、dev/main 或生产数据，也不修改基础循环。

## 参考与选择策略

参考 SICA 的历史优化器、独立目标、归档和重复评测，以及 auto-harness 的单一假设、受保护评测设施、回归集与停滞停止。当前使用 Git 归档/分离工作区，验证集正增益才提升，持平不提升；holdout 只在显式调用时评测，不反馈自动搜索。参考固定源码：[SICA runner，ed8275d](https://github.com/MaximeRobeyns/self_improving_coding_agent/blob/ed8275dca4d3c5dbf77229964351fe9b424797dc/runner.py) 与 [auto-harness，52360db](https://github.com/neosigmaai/auto-harness/blob/52360dbbeb8cea8886d90778e634a145c51da735/program_templates/base.md)。

## 初始化和代际过程

先提交干净源码基线，实验目录、manifest、验证器和留出数据放仓库外。配置明确目标、editable、隔离后端、优化模型、检查命令、train/validation/holdout 任务、重复数、次数、停滞/回归阈值和费用/超时。argv 列表保护有空格的 Windows 路径，外部脚本用绝对路径。

退出码评分以 exit 0 为成功；JSON 评分需写 score/cost，缺失/非零退出/超时不能促成提升，非法分数停止。任务 ID 与重复数保持分母，不因遗漏提高得分。每代记录优化器/源码 SHA、差异、检查、逐题结果、费用和决定；每次检查/试验使用固定 SHA 的全新检出，不受脏文件影响。

## 隔离、预算与恢复

Docker/Bubblewrap 包裹整个历史优化 Python 进程，不只隔离 Bash。优化器只写指定 worker 输出，控制器和验证器日志在外；忽略不可信进程租约，拒绝结果链接。外部检查命令运行在宿主并需自行隔离不可信候选。local 仅适合可信开发，不构成安全边界。

调用前预留费用界，未知/被终止请求保留预留，超额停止后续。模型或演化代码可能破坏自身计数，硬限额需供应商配额/独立网关。控制器安装源码、依赖、外部验证器有指纹，变化需要新实验。依赖清单和控制器/测试定义排除在当前演化范围；模型、工具、上下文、记忆适配和委派实现可在 editable 内改进。

原子 state 和 OS 锁防双控制器；恢复按 PID 与创建时间清理自己子进程/容器，中断候选保留，不自动恢复或提升。自动优化器关闭可变 Hindsight 召回，评测需要固定记忆/数据快照。回滚只改变后续实验选择，不迁移生产数据库。审核差异后从 dev 任务分支走 PR 发布。

## 真实 auto-harness 适配

在候选目录外准备 `https://github.com/neosigmaai/auto-harness.git` 的干净检出，并执行 `git checkout 52360dbbeb8cea8886d90778e634a145c51da735`。可信绝对路径 `factory.py:create` 接受 `(upstream, candidate, split)`，返回 `upstream.BenchmarkRunner`，连接候选的真实 VERA Runtime，不能仍调用示例 Agent。适配器会校验上游 SHA 与干净状态；`VERA_AUTO_HARNESS_CHECKOUT` 指向此检出可运行真实上游接口测试。通用上游没有统一实际费用接口，适配器按声明界计费，遗漏任务算零。设置专用 checkout 环境变量可实测该接口；本地协议/CLI 测试不替代真实 benchmark 或模型效果。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```yaml
objective: Improve task completion while preserving existing tool behavior.
sandbox: auto
docker_image: vera-evolution-runtime:local
credential_env: [DEEPSEEK_API_KEY]
editable: [src/vera/agents/, src/vera/tools/]
optimizer:
  model:
    model_class: litellm
    model_name: deepseek/deepseek-flash
    model_kwargs:
      max_tokens: 4096
      timeout: 60
      num_retries: 0
  agent:
    agent_class: stateful
    step_limit: 30
checks:
  - ['{python}', '-m', ruff, check, src]
  - ['{python}', '-m', compileall, '-q', src]
tasks:
  - id: existing-file-tool
    split: train
    command: ['{python}', '/absolute/trusted/evaluate.py', '--candidate', '{candidate}', '--task', '{task_id}', '--result', '{result}']
    scoring: json
    max_cost: 0.02
  - id: unseen-file-tool
    split: validation
    command: ['{python}', '/absolute/trusted/evaluate.py', '--candidate', '{candidate}', '--task', '{task_id}', '--result', '{result}']
    scoring: json
    max_cost: 0.02
  - id: final-acceptance
    split: holdout
    command: ['{python}', '/absolute/trusted/evaluate.py', '--candidate', '{candidate}', '--task', '{task_id}', '--result', '{result}']
    scoring: json
    max_cost: 0.02
repeats: 3
max_iterations: 10
patience: 5
min_gain: 0.02
regression_threshold: 1.0
cost_limit: 5.0
optimizer_cost_limit: 0.25
optimizer_timeout: 600
```

```bash
vera-extra evolution prepare-runtime --source .
vera-extra evolution init ../vera-experiment --source . -c ../evolution.yaml
vera-extra evolution baseline ../vera-experiment
vera-extra evolution run ../vera-experiment --iterations 3
vera-extra evolution status ../vera-experiment
vera-extra evolution cancel ../vera-experiment
vera-extra evolution run ../vera-experiment --resume
vera-extra evolution holdout ../vera-experiment
vera-extra evolution rollback ../vera-experiment baseline
vera-extra evolution export ../vera-experiment candidate.patch
```

```text
python -m vera.evolution.auto_harness --checkout /trusted/auto-harness --factory /trusted/factory.py:create --candidate CANDIDATE --split train --task-id TASK_ID --result RESULT_JSON --cost-bound 0.05
```
