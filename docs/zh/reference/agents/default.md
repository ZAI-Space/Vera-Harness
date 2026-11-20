[English](../../../reference/agents/default.md) · [简体中文](default.md)

# DefaultAgent

!!! abstract "API 参考"

    本页展示 VERA 当前源码生成的接口。标识符、类型签名和源码注释保持源语言，中文说明不改动调用契约。先确认组件配置及依赖，再按接口传参。

Agent 协调模型与工具循环。交互类增加审批/用户输入，状态层采用观察适配，持续目标与定时任务位于调用方。详情见[控制流](../../advanced/control_flow.md)。

::: vera.agents.default.AgentConfig
::: vera.agents.default.DefaultAgent
::: vera.exceptions.InterruptAgentFlow
::: vera.exceptions.Submitted
::: vera.exceptions.LimitsExceeded
::: vera.exceptions.FormatError
::: vera.exceptions.UserInterruption

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```python
--8<-- "src/vera/agents/default.py"
```
