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

## 默认助手与完成条件

桌面默认配置在 `vera.yaml` 上叠加 `desktop/assistant.yaml`。默认助手可以直接回答问答、写作和解释类请求。需要项目操作时，再使用已注册工具。全局规则与记忆继续加载；代码任务仍要求先阅读相关实现并验证修改。

系统提示按职责组织为身份、工具使用、任务边界、回复和环境信息，参考了 [Pi 的提示构建方式](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/system-prompt.ts)，没有复用其执行循环。原有“阅读代码、复现、修改、测试”流程保留在可选的“编程任务流程”Subagent 模板中。创建并启用角色后，主助手才可按需委派该角色。

模型适配器通过 `allow_text_final` 接受正常完成且非空的纯文本回复。Agent 使用已有的 `Submitted` 结束机制生成完成记录。工具回复继续走原有的请求、工具执行、观察结果和再次请求循环。空回复、截断和非法工具参数仍需纠正；不会直接标记成功。

Plan、Goal、只读任务和 Subagent 保留各自的完成工具。基准测试默认配置仍要求工具调用。用户通过 `-Config` 提供的任务提示词继续保留。

桌面 LiteLLM 请求使用 `cost_tracking: tokens`。该模式只记录服务商返回的输入、输出与缓存 Token，不查询价格目录。未知模型价格不会使已返回的内容失败。`cost=0` 是旧接口的兼容值；`cost_known=false` 表示没有确定金额，不能解释为免费。逐次 Token 用量进入统计账本，轨迹中的 `info.model_stats.token_usage` 同时保留运行汇总。格式校验失败的已消耗响应也计入统计。

需要美元预算的评测或 RSI 任务仍可使用原有严格计费配置。桌面 Token 统计不等同于服务商账单。

## 接口地图

| 界面操作 | 请求与返回字段 | 后端边界 |
| --- | --- | --- |
| 新建会话 | `createSession({options:{cwd,provider?,modelId?,thinkingLevel?}})` → `SessionMeta` | `DesktopStore` |
| 历史与恢复 | `getSessionBaseline({sessionId})` → `meta,sequence,hydrationToken,transcript,permissionMode` | `Sessions`、SQLite |
| 发送与停止 | `prompt({sessionId,text,document?,images?,interrupt?})`、`abort({sessionId})` | 独立 worker、`open_agent_runtime` |
| 审批 | `requestId,answer`；可附匹配的 `sessionId` → 已裁决事件 | 按会话绑定的 stdin 回复，仅允许一次或拒绝 |
| 文件附件 | `listProjectFiles({cwd})` → 项目相对路径；输入文档使用 `file.path` | `ProjectFiles` |
| 模型配置 | 连接标识、协议、地址、模型定义；执行选择器仅列出已认证且可见的模型 | `Providers`、私有凭据库 |
| 角色编辑 | 名称、指令、模型引用、工具、技能与预算 | `SubagentConfig`、共享 Runtime |
| MCP 市场 | 显式搜索、预览和添加；新服务默认停用 | `DockerCatalog` |
| MCP 配置 | 用户级、stdio 或 URL、direct 暴露、启用状态、显式测试连接 | Python MCP SDK；测试仅初始化并读取工具清单 |
| 插件 | GitHub / Gitee 市场、安装、启用、停用、卸载 | `PluginManager` |
| 沙箱 | 配置与可用性、原因；不可用项禁选 | `SandboxProfiles` |
| 定时任务 | 频率、项目、模型、时区 → 任务与运行快照 | `JobStore`、独立调度服务 |
| Plan / Goal | `/plan`、`/goal` 与模式选择 | 复用已有模块，不替换循环 |
| 导出、分支与撤回 | 展示历史、目标消息之前的模型上下文 | SQLite、不可变运行凭据 |

完整 TypeScript 契约位于 `desktop/src/contracts/`，Python 分发位于 `src/vera/desktop/`。界面偏好保存在 Electron 用户目录；后端配置、会话、安全展示导出、凭据库和运行记录保存在 VERA 私有桌面状态目录。

技能市场通过 skills CLI 搜索和安装，桌面通过资源目录加载已安装的 Skills。

## 常用桌面操作

1. 打开“设置 → 行为”，选择新任务的默认权限和检测到的本机 Shell。首次执行前必须成功保存权限。已保存但暂不可用的 Shell 保留显示，由用户选择替代项。
2. 打开“规则与记忆”，创建条目并保存，通过开关启停。条目在重启后保留。删除需要确认；保存或删除失败时保留当前条目供重试。不要把凭据放进指令。
3. 打开“联网工具”，选择服务商，填写密钥或 SearXNG 实例地址，先保存再测试。留空密钥会保留已存密钥；删除时使用明确的移除操作并保存。连接测试成功不等于完整 Agent 任务成功。
4. 打开“统计数据”，按项目和时间范围查看已记录用量。缺失计数表示未知；连接测试和 VERA 外部工具计费不计入。缓存分母以页面提示为准。
5. 从会话上下文菜单打开图片维护，先预览体积估算，再确认压缩。保留备份；压缩后对话已变化时会拒绝恢复。回应丢失时，先查看已有操作记录，再决定是否重新提交。

远程账号配对见[渠道接入](channels.md)，可选任务应用见[任务面板](taskboard.md)。仅打开设置不会启动这些传输。

## 传输与流式输出

服务仅监听 `127.0.0.1`。`/health`、`/invoke`、`/events?after=<cursor>` 均需 bearer token，并拒绝跨来源浏览器请求。token 仅存在 Electron 主进程。成功返回 `{result: ...}`；失败返回明确错误，不表示操作完成。

长轮询在事件到达时立即唤醒。服务商 SSE 片段在回复完成前转换为 `thinking_delta`、`text_delta` 和工具参数增量；工具边界与 `turn_end` 保持顺序。完整回复仍由原模型解析器校验，校验完成前不会执行工具。PI-Desktop 调研与展示规则见[流式呈现](desktop-streaming.md)。

事件包含 `sessionId,sequence,event`。游标缺口或服务重启触发基线恢复，不自动重放有副作用的请求。停止会终止所属 worker 进程树，保留已收到的文字并清理审批。会话之间有独立 worker 和模型上下文；运行期间最多排队 20 条后续消息。传入 `interrupt: true` 可停止当前任务并优先执行新消息；详见[队列与恢复契约](desktop-api.md#应用方法)。

## 权限与边界

`confirm` 请求审批，`yolo` 不逐项审批，`human` 执行用户手动输入的命令。审批提供单次允许和拒绝。沙箱使用用户配置的隔离环境，运行前需安装对应后端。

界面统一显示 Human、Confirm、Yolo。已有会话的权限选择保存到后端并在重新打开时恢复；新会话继承行为设置。模型连接中的可用目录与执行选择器分开：未配置凭据、隐藏或已删除的模型不进入选择器。用户 Skills 不要求先创建会话；启用插件贡献的 Skills 也纳入资源目录。

MCP 的“测试连接”会启动所配置的 stdio 进程或连接所配置的 URL，读取工具清单后关闭，不调用工具，也不自动启用服务。该结果是带时间的检查记录，不代表常驻连接。参数支持 JSON 字符串数组，带空格的 Windows 路径应作为一个数组项。修改配置会清除旧检查记录。

后台定时任务需明确选择 `yolo`，每次使用独立上下文。保存后保持暂停，再手动启用；手动任务使用立即运行。调度携带本机时区，并将界面的周一序号转换为 cron 序号。调度服务有独立生命周期，关闭桌面不会停止已启用的调度。

API 配置依次填写服务商、API Key 和模型 ID。配置名称由服务商或自定义接口地址自动生成，不再提供模型显示名称输入。

前端按[桌面 API](desktop-api.md)的方法表接入。MCP 配置从下次任务生效，连接检查保存探测结果与时间。Hindsight 配置见[记忆文档](hindsight-memory.md)。

## 已接入的设置与远程能力

行为设置可检测已安装的 Bash，Windows 也可选择检测成功的 WSL Bash；不会静默安装或替换 Shell。全局规则与记忆由用户显式维护；统计页记录 Token，不将未知金额解释为免费。

WSL 通过 `WSLENV` 接收显式配置的环境变量覆盖项与 Python 编码设置，不会整体复制 Windows 环境；已有的 `WSLENV` 标志保持生效。

跨设备互联默认关闭，开启后使用独立 LAN 监听和配对 token；远程控制需另行开启。微信与飞书使用已有渠道的配对与用户白名单。详见[接口边界](desktop-api.md)。可选[任务看板](taskboard.md)独立安装，执行结果进入待审核。

## 验证

安装依赖并构建后，在 `desktop/` 内执行 `npm run test:ui`。命令在独立临时目录启动 Electron、Python 服务和本地模型协议服务，操作设置与任务提交，并核对界面、SQLite 和文件变化。测试使用隔离配置，报告、失败截图与日志保存在命令输出的 `EVIDENCE` 路径。

集成测试覆盖 HTTP、worker 进程、SSE 流式、审批、取消、持久化和调度。TypeScript 契约测试消费 Python worker 事件并核对渲染状态；Electron 测试检查正文显示、工具审批、Bash 输出和思考折叠。见[流式回归测试](desktop-streaming.md)。
