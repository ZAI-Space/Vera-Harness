[English](../frontend-integration.md) · [简体中文](frontend-integration.md)

# 前端对接

!!! abstract "同一 Runtime，两个入口"

    仓库包含 `desktop/` Electron + React 桌面端与独立 Python 桌面服务，终端入口继续保留。Electron 不导入智能体 SDK，renderer 不执行工具。

## 启动桌面端

使用 Python 3.12、Node.js 24 LTS 和 Bash；Windows 使用 Git Bash。先安装依赖：

```bash
uv venv --python 3.12
uv pip install -e '.[full,channels]'
cd desktop
npm ci
cd ..
```

PowerShell：`powershell -File scripts/start-desktop.ps1`。Git Bash、Linux/macOS Bash：`bash scripts/start-desktop.sh`。Windows 的 Bash 入口由 PowerShell 脚本负责进程生命周期。已有后端配置可通过 Windows 的 `-Config path.yaml` 或 Unix 的 `--config path.yaml` 传入。智能体任务需先在模型设置中配置并选择模型；`human` 可直接执行手动输入的 Bash 命令。

启动器只管理自己启动的服务及子进程，使用带认证的回环连接文件，构建桌面端并在退出时清理连接文件，不安装 Docker 或 Bubblewrap。

## 接口地图

| 界面操作 | 请求与返回字段 | 后端边界 |
| --- | --- | --- |
| 新建会话 | `createSession({options:{cwd,provider?,modelId?,thinkingLevel?}})` → `SessionMeta` | `DesktopStore` |
| 历史与恢复 | `getSessionBaseline({sessionId})` → `meta,sequence,hydrationToken,transcript,permissionMode` | `Sessions`、SQLite |
| 发送与停止 | `prompt({sessionId,text,document?,images?})`、`abort({sessionId})` | 独立 worker、`open_agent_runtime` |
| 审批 | `requestId,answer`；可附匹配的 `sessionId` → 已裁决事件 | 按会话绑定的 stdin 回复，仅允许一次或拒绝 |
| 文件附件 | `listProjectFiles({cwd})` → 项目相对路径；输入文档使用 `file.path` | `ProjectFiles` |
| 模型配置 | 连接标识、协议、地址、模型定义；凭据仅回传是否已配置 | `Providers`、私有凭据库 |
| 角色编辑 | 名称、指令、模型引用、工具、技能与预算 | `SubagentConfig`、共享 Runtime |
| Skill / MCP 市场 | 显式搜索、预览、安装或添加；MCP 保存后默认停用 | `SkillMarket`、`MCPRegistry` |
| MCP 配置 | 用户级、stdio 或 URL、direct 暴露、启用状态 | 下次任务中的 Python MCP SDK |
| 插件 | GitHub / Gitee 市场、安装、启用、停用、卸载 | `PluginManager` |
| 沙箱 | 配置与可用性、原因；不可用项禁选 | `SandboxProfiles` |
| 定时任务 | 频率、项目、模型、时区 → 任务与运行快照 | `JobStore`、独立调度服务 |
| Plan / Goal | `/plan`、`/goal` 与模式选择 | 复用已有模块，不替换循环 |
| 导出、分支与撤回 | 展示历史、目标消息之前的模型上下文 | SQLite、不可变运行凭据 |

完整 TypeScript 契约位于 `desktop/src/contracts/`，Python 分发位于 `src/vera/desktop/`。界面偏好保存在 Electron 用户目录；后端配置、会话、安全展示导出、凭据库和运行记录保存在 VERA 私有桌面状态目录。

## 传输与流式输出

服务仅监听 `127.0.0.1`。`/health`、`/invoke`、`/events?after=<cursor>` 均需 bearer token，并拒绝跨来源浏览器请求。token 仅存在 Electron 主进程。成功返回 `{result: ...}`；失败返回明确错误，不表示操作完成。

长轮询在事件到达时立即唤醒。服务商 SSE 片段在回复完成前转换为 `thinking_delta`、`text_delta` 和工具参数增量；工具边界与 `turn_end` 保持顺序。完整回复仍由原模型解析器校验，校验完成前不会执行工具。PI-Desktop 调研与展示规则见[流式呈现](desktop-streaming.md)。

事件包含 `sessionId,sequence,event`。游标缺口或服务重启触发基线恢复，不自动重放有副作用的请求。停止会终止所属 worker 进程树，保留已收到的文字并清理审批。会话之间有独立 worker 和模型上下文；运行期间可排队一条后续消息。

## 权限与边界

`confirm` 请求审批，`yolo` 不逐项审批，`human` 执行用户手动输入的命令。当前审批提供允许一次和拒绝，尚未开放持久命令白名单编辑。沙箱是用户配置的隔离环境，没有可用后端时禁用选择，不自动下载安装。

后台定时任务需明确选择 `yolo`，每次使用独立上下文。保存后保持暂停，再手动启用；手动任务使用立即运行。调度携带本机时区，并将界面的周一序号转换为 cron 序号。调度服务有独立生命周期，关闭桌面不会停止已启用的调度。

OAuth 账号订阅、SSH、局域网远程控制、PI 扩展、codemode/deferred MCP 和手动上下文压缩尚未由当前适配器提供，界面入口禁用或明确拒绝不支持的操作。MCP 配置从下次任务生效，设置页不伪报常驻连接状态。这些限制与已有 Hindsight 记忆及上下文模块分开。

## 验证

仓库包含真实 HTTP/进程、SSE 流式、审批、中止、持久化与调度适配测试。TypeScript 集成测试消费实际 Python worker 产生的事件，核对最终展示投影。Electron 联调使用本机协议测试服务，另行检查实际正文、工具审批、Bash 输出和思考折叠。另一次真实 DeepSeek 运行通过桌面服务与 worker 完成流式输出、工具执行和文件创建，并以 `Submitted` 结束，见[流式验证证据](desktop-streaming.md#验证证据)。其他服务商与市场可达性仍需相应凭据及网络验收。
