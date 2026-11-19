[English](../../usage/python_bindings.md) · [简体中文](python_bindings.md)

# Python 调用

!!! abstract "优先共享 Runtime"

    open_agent_runtime 统一组装模型、环境、插件、MCP、Skill 和 Subagent，context 管理连接与清理，须在运行期间保持打开。直接构造基础 Agent 时需要完整 system/instance 模板，不能照抄缺参数的旧示例。

模型与凭据仍需真实配置。非交互调用选择正确 Agent 类和明确权限；confirm 需要人类输入适配。状态观察选择 Stateful 类。CLI 命名与运行时包迁移见[兼容说明](../advanced/v2_migration.md)，更多扩展见[组件手册](../advanced/cookbook.md)和[前端接口](../frontend-integration.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```python
from vera.config import get_config_from_spec
from vera.runtime import open_agent_runtime

config = get_config_from_spec("vera.yaml")
config["model"] = {"model_class": "litellm", "model_name": "openai/YOUR_MODEL"}
with open_agent_runtime(config) as runtime:
    result = runtime.agent.run("Inspect the project and report findings")
```
