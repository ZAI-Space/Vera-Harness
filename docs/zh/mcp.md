[English](../mcp.md) · [简体中文](mcp.md)

# MCP 工具

终端与共享 Runtime 支持在 Bash、网页工具旁加载 MCP。安装 `.[mcp]` 后，通过 YAML 配置 stdio 可执行程序/参数，或 Streamable HTTP 地址。Windows 可以为 `command` 设置 server 的 python.exe 完整路径；`cwd` 指定服务器工作目录。

## 配置和认证

`env_from` 是必需的 stdio 环境变量名，`optional_env_from` 只转发已经存在的变量。远程 `bearer_token_env` 指向 Bearer 密钥变量；`headers_from` 将 API 请求头映射到变量名。只保存名称，不将凭据值写进命令和 YAML。远程携带凭据必须用 HTTPS，不能覆盖 HTTP/MCP 协议头。只支持一种传输，OAuth、SSE 和 bundle/OCI 不因市场接入自动获得支持。

`allow_tools` 不填时暴露发现的工具，空列表暴露零个，拼错名称启动失败。工具名通常是 `mcp_服务_工具`。confirm 模式对命名调用审批。stdio 运行于宿主子进程权限，远程调用把实参发送到服务；沙箱策略需要分别允许可信的宿主/远程服务器。

## 市场与生命周期

通过 `vera-extra mcp search/inspect/add` 从官方 Registry 查找、预览并添加；添加的服务不立即连接，先用 `/mcp NAME` 或 `mcp_selection` 选择。已有显式配置优先。见[市场](markets-and-modes.md)。

每次任务组装连接和发现工具，任务退出关闭连接。`timeout` 用于请求和发现。结构化结果显示 JSON，文本直接显示，其他类型用占位符；结果限制为 6000 字符并标记截断。协议错误与服务执行错误保留为观察，未知发送效果不可盲目重放。

## 配置、命令与源码示例

```bash
python -m pip install -e ".[mcp]"
```

```yaml
mcp_servers:
  local:
    command: python
    args: [local_server.py]
    allow_tools: [echo]
  docs:
    url: https://mcp.example.com/mcp
    bearer_token_env: DOCS_MCP_TOKEN
    allow_tools: [read_document]
    timeout: 30
```

```bash
vera -c vera.yaml -c mcp.yaml
```
