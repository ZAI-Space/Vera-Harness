[English](../markets-and-modes.md) · [简体中文](markets-and-modes.md)

# 能力市场与显式运行模式

## 发现、预览与添加

MCP 默认接官方 Registry，Skill 默认接 skills.sh；插件仍只提供 GitHub 和 Gitee。参考 Hermes 把搜索、检查、安装分开。搜索不启动服务器、不执行下载内容。MCP latest 查询显式选择最新记录并支持游标，预览发布者版本、传输、输入要求和依赖；npm/PyPI 包固定版本，HTTP 的运行端点仍由远端发布者维护。

添加 MCP 只保存设置，`/mcp NAME` 或 mcp_selection 后才连接。显式 mcp_servers 优先。缺少 Node/npx 或 uv/uvx 需用户准备；首次启动这些工具可能拉取已固定包，保存设置不安装系统依赖。远程认证只引用环境变量，要求 HTTPS，不能覆盖协议头。

Skill 从 skills.sh 的 GitHub 来源按提交下载，校验 YAML frontmatter、路径和大小，保存支持文件与来源摘要，不运行安装脚本。现有内容不覆盖，修改过的内容不自动删除。`/mcp search/add`、`/skill search/add` 为显式用户操作；补全仅读本地。Python 接口可用于前端设置页。

## Plan 模式

`/plan 请求` 只读查看项目，生成包含目标、当前实现、路径、步骤、验证命令、风险与问题的 Markdown，写到 `.vera/plans/`。能力表只含 project_files、project_read、plan_finish；不暴露 Shell、MCP、Subagent 写入。没有参数时使用上一任务，缺少上下文则要求明确请求。完成后不会自动实施；打开 plan 会暂停活动 goal。

## Goal 模式

`/goal 目标` 保存当前对话的持续目标。每轮执行完成后，判定器根据答复和近期工具结果返回 done/continue/blocked；需要继续时，在轮次、费用和时间预算内开始下一轮。无效判定或服务异常会暂停目标。使用 `/goal status` 查看状态，使用 `/goal pause` 暂停执行。

status/show 查看状态；pause 停止后续轮次，resume 保留上下文并重置本次预算，clear 删除目标。`-- 文本` 转义开头控制词。/stop 暂停并使用既有取消路径。运行时选择改变后必须新建目标，避免跨轮暗中改变权限或能力。崩溃中断需核实副作用后新建，不能盲目重放。

## 会话、权限与调用

前端每个 chat 指定独立 terminal.session_id，默认 default；状态按工作区和会话持久化，公开状态不含私有消息。goal 配置 max_turns 默认 20、cost_limit 默认 3、timeout 默认 1800，可设置完整 judge_model。已经发出的 provider 请求可越过剩余预算，不能视作供应商硬限额。

confirm/yolo/human 与 plan/goal 分离；human 需先选择模型驱动模式。审批提示内切换模式会先结束旧任务，再重新组装限制后的 Runtime。普通后续任务退出显式模式。`drive_goal` 接收宿主 run_turn 回调，不内置后台服务或桌面传输。下方保留市场命令、配置和控制示例。

## 配置、命令与源码示例

```bash
vera-extra mcp search context7
vera-extra mcp inspect io.github.upstash/context7
vera-extra mcp add io.github.upstash/context7
vera-extra mcp list
vera-extra mcp remove context7
vera-extra skills search find-skills
vera-extra skills inspect vercel-labs/skills/find-skills
vera-extra skills install vercel-labs/skills/find-skills --ref COMMIT_SHA
vera-extra skills remove find-skills
```

```text
/plan Add streaming responses to this project
/goal Implement streaming responses and verify the regression tests pass
/goal status
/goal pause
/goal resume
/goal clear
```

```yaml
terminal:
  session_id: project-chat-1
goal:
  max_turns: 20
  cost_limit: 3
  timeout: 1800
  # Optional complete model configuration for a separate judge:
  # judge_model: {model_class: litellm, model_name: openai/your-judge}
```
