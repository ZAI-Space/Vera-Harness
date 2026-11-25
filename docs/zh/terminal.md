[English](../terminal.md) · [简体中文](terminal.md)

# 终端文件上下文与命令

在项目目录启动 `vera`，输入任务、文件引用或斜杠命令。Tab 搜索并选择候选，Esc 后 Enter 提交多行内容。审批提示中原有 `/h /m /u /c /y` 继续有效。

## 项目文件

`@src/main.py` 或 `@"docs/design notes.md"` 仅引用当前工作区内的文件，搜索不区分大小写，Git 项目列表尊重 ignore 规则。路径用正斜杠。绝对路径、上级跳转、越界链接、依赖目录及常见凭据文件被拒绝。限制为 10 个 UTF-8 文件，每个 32 KiB，总共 128 KiB；整个选择先校验，失败不会发送部分上下文。

## 选择和控制

| 命令 | 作用 |
| --- | --- |
| `/skill`、`/mcp`、`/plugin` | 列出并选择可用能力；逗号多选，按接口支持 all/none |
| `/model` | 选择 `terminal.models` 中已配置模型 |
| `/subagent ROLE [任务]` | 选择角色，或立即提交委派任务 |
| `/permissions confirm|yolo|human` | 设置下一任务的操作模式 |
| `/sandbox [NAME|none]` | 查看具名环境状态或选择本地 |
| `/plan [请求]` | 只读调研并保存实现计划 |
| `/goal 目标|status|pause|resume|clear` | 显式设置、查看、暂停或恢复目标 |
| `/new`、`/stop`、`/help` | 新对话、停止任务、查看帮助 |

`/mcp search/add` 和 `/skill search/add` 是用户显式发起的市场操作；Tab 和普通目录选择不联网。模型、插件、MCP、权限或沙箱选择只作用于下一次组装，不修改当前执行环境。`//` 转义字面斜杠。模型输出或文件内容里的命令不会被当成用户斜杠操作。

## 权限与前端复用

`confirm` 审批操作，`yolo` 全部执行，`human` 手动输入命令，不是“全审批模式”。历史只读策略仍可通过后端配置使用。前端通过 `TerminalSession.catalog/process/runtime_config`、`ProjectFiles` 和 `open_agent_runtime` 对接；这些 Python 边界不要求 prompt-toolkit。见[前端说明](frontend-integration.md)。

## 配置、命令与源码示例

```text
Review @src/main.py and @"docs/design notes.md"
```

```yaml
terminal:
  models:
    fast:
      model_class: litellm
      model_name: openai/your-fast-model
    reasoning:
      model_class: litellm
      model_name: openai/your-reasoning-model
```
