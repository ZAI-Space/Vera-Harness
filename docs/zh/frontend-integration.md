[English](../frontend-integration.md) · [简体中文](frontend-integration.md)

# 前端对接

!!! abstract "共享能力，明确传输边界"

    已有终端和可复用 Python 接口，尚不提供完整桌面 HTTP/WebSocket 服务。显示名称一致不代表已完成联调。不要通过解析终端彩色文字获取状态。

## 接口地图

| 前端动作 | 后端接口 | 要点 |
| --- | --- | --- |
| @搜索/添加 | ProjectFiles.list/attach | 项目内路径、UTF-8、大小/敏感文件限制 |
| /命令选择 | TerminalSession.catalog/process/runtime_config | 下一任务生效，运行中不重配 |
| 执行 | open_agent_runtime + agent.run | 宿主管理生命周期、审批和取消 |
| 状态事件 | StatefulAgent.subscribe/state | 副本，回调不改执行 |
| 历史/恢复 | RunStore | unknown 必须核对，不自动重放 |
| 能力市场 | SkillMarket/MCPRegistry/MCPServices | 显式添加和选择，凭据留后端 |
| 插件 | PluginManager | 安装不等于启用 |
| 沙箱设置 | SandboxProfiles | 只显示已配置选项并检查可用性 |
| 持续目标 | GoalStore/drive_goal | 每个聊天独立 session_id |
| 定时任务 | JobStore/Scheduler | 独立服务所有权，结果本地存储 |

## 审批与环境

明确展示 confirm、yolo、human，human 是手动命令，不是“完全审批”。plan 只提供只读查看和计划写入，goal 沿用当前权限。沙箱是另一个选择器；没有配置或不可用时禁用并显示原因，不从聊天强装后端。开始执行时重新校验工作区与可用性。

## 适配层责任

为消息定义任务/会话 ID、事件封装、取消所有权和审批请求/答复。阻塞任务放后台执行线程或进程，转发事件到 UI/网络线程，完成/异常都关闭 Runtime。每个聊天独立 ID、每次运行新轨迹路径，重连后继续如实表达 unknown。

返回安全目录与状态，不能向不可信客户端暴露完整配置、token、JobStore 内部定义/执行快照或堆栈。公开接口不表示远程授权已经完成。实际 UI 验收覆盖 @文件、三种权限、各能力选择、沙箱灰态、状态、取消、恢复、计划、目标、多会话与传输重启；后端单测不能替代。
