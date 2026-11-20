[English](../agent-state.md) · [简体中文](agent-state.md)

# Agent 状态观察

!!! abstract "观察层，不替换循环"

    `stateful` 与 `stateful_interactive` 在既有运行方法外发布状态快照与生命周期事件。原有动作顺序、停止条件、异常、预算与轨迹语义保留；工厂里的 default/interactive 仍选择原类。

设计参考 pi-agent 的状态/事件分离，固定来源链接见英文版与源代码说明；这是 Python 观察适配器，不是移植异步 Pi Runtime。通过 `--agent-class stateful_interactive` 启用，Python 调用使用 `subscribe` 并在结束后 unsubscribe。

## 状态和事件

状态包括 idle、running、querying、executing、waiting_for_input、completed、stopped、failed、cancelled。completed 对应 Submitted，预算等其余正常停机对应 stopped；正常返回 Cancelled 或逃逸 KeyboardInterrupt 对应 cancelled；连续格式失败/其余逃逸异常为 failed。消息、计数、费用、等待工具、退出原因来自原 Agent。run 再次执行会替换对话，但原类计数和墙钟基线不自动重置。

事件包括 agent/turn/query/tools 的 start/end、messages_added、input_requested/received。序号跨运行增加，通知在状态更新后同步发送，每个订阅者得到脱离实时状态的副本。订阅者异常记录日志，不改变执行；订阅回调不能推进或修改 Agent。直接 step/query 也可观察，而 is_running 专指 run 包装范围。

## 前端对接

`agent.state.to_dict()` 提供序列化快照，订阅回调由应用转发到 UI 线程或传输层。快照可能含项目内容与工具实参，不应无差别广播。状态观察本身不创建线程、网络服务或取消机制。见[前端对接](frontend-integration.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```powershell
.\start.cmd --agent-class stateful_interactive
```

```bash
bash scripts/start.sh --agent-class stateful_interactive
```

```python
from vera.agents.stateful import StatefulAgent

agent = StatefulAgent(model, environment, **agent_config)
unsubscribe = agent.subscribe(
    lambda event: print(event.type, event.state.status.value)
)
result = agent.run(task)
print(agent.state.status.value, agent.state.n_calls, agent.state.cost)
snapshot = agent.state.to_dict()
unsubscribe()
```
