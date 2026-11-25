[English](../../advanced/cookbook.md) · [简体中文](cookbook.md)

# 组件扩展手册

!!! abstract "先组合，再继承"

    选择 Agent、Model、Environment，在入口脚本组装。需要终端一致的插件、MCP、Skill、Subagent 和沙箱策略时，使用共享 Runtime，避免手写一套不一致的生命周期。

## 完整构造与工具

基础 Agent 的 system_template 与 instance_template 不是可省略字段；从内置配置加载后再构造。InteractiveAgent 还需要输入适配和权限。创建 Docker 类不意味着后端/镜像已准备。

命名能力优先用 ToolSpec 和注册表，Schema 与分派共享。handler 返回 output/returncode/exception_info，或有意抛出流程异常。每个注册表绑定独立原生工具模型，不在 Bash 字符串内猜 Python 函数调用。

## 状态和自定义组件

UI 状态用 Stateful 订阅，订阅者不能修改执行；独立上下文用 Subagent，流程指令用 Skill。自定义组件实现 Protocol 所需 query、消息格式、execute、template vars 与 serialize，工厂接受类路径。默认入口覆盖变量仍支持自定义模块。副作用收据通过 RunStore 跟踪，未知结果不伪装成功。

## 配置、命令与源码示例

```python
from vera.agents.default import DefaultAgent
from vera.config import get_config_from_spec
from vera.environments.local import LocalEnvironment
from vera.models import get_model

config = get_config_from_spec("default.yaml")
agent = DefaultAgent(
    get_model(config={"model_name": "openai/YOUR_MODEL", "model_class": "litellm"}),
    LocalEnvironment(cwd="."),
    **config["agent"],
)
result = agent.run("Inspect the project")
```

```python
from vera.tools import ToolSpec, make_tool_registry

registry = make_tool_registry(agent.env)
registry.register(
    ToolSpec("lookup_status", "Read local application status", {"type": "object"}),
    lambda arguments: {"output": "ready", "returncode": 0, "exception_info": ""},
)
agent.tool_registry = registry
agent.model.bind_tool_registry(registry)
```
