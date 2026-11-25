[English](../web-tools.md) · [简体中文](web-tools.md)

# 工具注册表与网页 Provider

Bash 承担当前环境中的文件读写、检索和构建。统一注册表把能力名称、JSON Schema 与执行处理器关联起来；模型看到的声明与分派校验来自同一注册表，工具调用 ID 连接轨迹中的请求和结果。

## 搜索与提取

搜索和提取可分别选择：SearXNG 用 `SEARXNG_URL`，实例需启用 JSON；Firecrawl 用 `FIRECRAWL_API_KEY`，支持搜索和 Markdown 提取；Tavily 用 `TAVILY_API_KEY`，可同时承担两者。仅配置本次需要的 Provider，密钥放环境或现有私有配置。

`web_search` 接收查询与 1–8 个结果上限，返回 URL、标题和摘要。`web_extract` 接收一个公共 HTTP(S) URL，返回最多 6000 字符 Markdown 并标记截断。查询或 URL 会交给所选服务。confirm 模式在提交前展示参数并审批；Bash 白名单不适用于命名工具。服务失败转为工具观察。

## 模型和扩展

使用 LiteLLM、OpenRouter 等原生工具调用适配器。文本动作适配器不能声明命名网页工具。模型请求在宿主端，Provider 获取网页并执行自己的网络限制。沙箱中网页能力需显式允许。

扩展时实现 `WebProvider.search/extract` 并调用 `register_web_tools`，或通过 `ToolSpec` 注册其他能力。每个注册表使用独立模型实例。下面保留运行命令与注册代码；PowerShell 设置变量采用 `$env:NAME = 'value'`，不要直接照抄 Bash export。

## 配置、命令与源码示例

```bash
export SEARXNG_URL=http://127.0.0.1:8080
bash scripts/start.sh -c vera.yaml -c web.search_provider=searxng
```

```bash
bash scripts/start.sh -c vera.yaml \
  -c web.search_provider=searxng -c web.extract_provider=firecrawl
```

```python
from vera.agents.default import DefaultAgent
from vera.tools import ToolSpec, make_tool_registry

registry = make_tool_registry(environment)
registry.register(
    ToolSpec("lookup_status", "Read the local application status", {"type": "object"}),
    lambda arguments: {"output": "ready", "returncode": 0, "exception_info": ""},
)
agent = DefaultAgent(model, environment, tool_registry=registry, **agent_config)
```
