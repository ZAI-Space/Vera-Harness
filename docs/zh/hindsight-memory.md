[English](../hindsight-memory.md) · [简体中文](hindsight-memory.md)

# Hindsight 项目记忆

使用运行中的 Hindsight 服务和项目专用 bank。默认本地地址 http://127.0.0.1:8888；云服务使用其地址和 bank 范围密钥。Hindsight 的模型独立于 VERA 任务模型配置。设置 HINDSIGHT_BANK_ID、HINDSIGHT_BASE_URL，通过 hindsight/hindsight_interactive 适配器启用。

## 记忆范围与上下文

当前会话保留完整轨迹；context_budget_chars 仅对每次传给模型的消息做软字符预算压缩，保留初始指令、近期完整工具组和用户约束。项目记忆来自主 bank，跨项目共享通过 memory_shared_bank_id 显式启用；通过 Python 独立构造 Hindsight Agent 时，可以传入独立主 bank 和共享客户端；内置角色委派目前创建 StatefulAgent 子实例，角色配置尚不支持 Hindsight bank 或客户端注入。凭据范围由调用者与服务管理。

初始任务会向配置 bank 查询，命中结果带来源添加到初始提示，进入轨迹并发给任务模型。bank 故障记录日志，继续使用可获得上下文。设置 memory_mode 为 disabled/facts/observations/reflect 控制模式。大消息或受保护的近期组可能超过软预算，完整轨迹不因压缩删除。

## 冲突、整理与人工管理

默认 prefer_observations 优先返回已整合观察，可能省略其来源原始事实。保留可用 fact/source ID、时间、bank 等来源信息；冲突时要求核对工作区并说明未解决分歧，不能把“新提到”自动视为正确。整合可能滞后。

reflect 使用 Hindsight 对事实、观察、mental models 的综合，并可能返回证据；需要接受记忆服务额外模型调用。CLI retain/recall/reflect/invalidate/restore 支持人工策展、文档 ID、context 和标签；不会自动摄入全部对话或自动淘汰事实。HINDSIGHT_API_KEY_FILE 或环境变量提供认证，远程凭据请求用 HTTPS。

## 比较验证

保持模型、任务、工作区、bank 快照、上下文预算和共享配置一致，仅改变 memory_mode。检查旧命令被替代、同等可信事实冲突、共享与项目决策冲突、子 Agent bank 隔离及长会话纠正。HTTP 测试只证明请求和注入契约，不证明真实 Hindsight 整合质量或模型效果；需对运行服务另做比较。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
export HINDSIGHT_BANK_ID=harness-project
export HINDSIGHT_BASE_URL=http://127.0.0.1:8888
./.venv/Scripts/vera-extra.exe memory retain 'Run local regression tests with pytest.'
./.venv/Scripts/vera-extra.exe memory recall 'How do I run regression tests?'
bash scripts/start.sh --agent-class hindsight_interactive
```

```bash
bash scripts/start.sh --agent-class hindsight_interactive \
  -c vera.yaml -c agent.memory_shared_bank_id=harness-shared \
  -c agent.context_budget_chars=24000
```

```bash
./.venv/Scripts/vera-extra.exe memory retain 'The project switched to pnpm.' \
  --document-id package-manager-decision --context 'Verified against pnpm-lock.yaml'
./.venv/Scripts/vera-extra.exe memory recall 'Which package manager is current?' --json-output
./.venv/Scripts/vera-extra.exe memory reflect 'Which convention is current, and what supports it?' --json-output
./.venv/Scripts/vera-extra.exe memory invalidate FACT_ID 'Verified obsolete against the workspace'
./.venv/Scripts/vera-extra.exe memory restore FACT_ID
```
