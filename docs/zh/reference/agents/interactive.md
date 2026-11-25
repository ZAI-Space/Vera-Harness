[English](../../../reference/agents/interactive.md) · [简体中文](interactive.md)

# Interactive

!!! abstract "API 参考"

    本页展示 VERA 当前源码生成的接口。标识符、类型签名和源码注释保持源语言，中文说明不改动调用契约。先确认组件配置及依赖，再按接口传参。

Agent 协调模型与工具循环。交互类增加审批/用户输入，状态层采用观察适配，持续目标与定时任务位于调用方。详情见[控制流](../../advanced/control_flow.md)。

::: vera.agents.interactive

## 配置、命令与源码示例

```python
--8<-- "src/vera/agents/interactive.py"
```
