[English](../faq.md) · [简体中文](faq.md)

# 常见问题

!!! question "Windows、Linux 都可以运行吗？"

    可以。Windows 本地命令使用 Git Bash，Linux 使用配置的 Shell。Docker、Bubblewrap 等可选后端需安装对应依赖。见[启动](windows.md)和[沙箱](sandbox.md)。

??? question "一定需要 Docker 吗？"

    不需要。local 使用当前用户的宿主机权限。沙箱由用户配置，显式请求的后端不可用时失败，不自动降级，也不因选择命令下载引擎或镜像。

??? question "只有 Bash 工具吗？"

    不是。除了 Bash 文件与构建操作，还支持网页工具、MCP、Skill、插件和 Subagent。命名工具要求原生工具调用模型；文本动作模型仍走 Bash 路径。

??? question "权限、模式和沙箱有何区别？"

    `confirm / yolo / human` 决定审批和操作来源；`/plan` 只读调研并保存计划；`/goal` 在预算内持续推进目标；沙箱决定命令隔离环境。几者不会隐式相互切换。

??? question "配置和 Shell 状态在哪里？"

    启动打印全局 `.env` 路径，`VERA_GLOBAL_CONFIG_DIR` 可以覆盖。环境变量优先，旧目录与变量名保留兼容。每条 Bash 是新进程，前一条的 cd/export 不会保留；配置 cwd/env 或在每条命令中显式指定。

??? question "目标和定时任务如何控制运行时间？"

    目标有轮次、费用和时间预算，定时任务有单次限额。限制在调用边界检查，已发出的请求可能超出剩余预算。后台调度需要服务持续运行，不能唤醒关机电脑。

??? question "桌面端如何连接后端？"

    Electron 桌面端通过带认证的本机回环 Python 服务接入会话、流式事件和 Runtime 操作。启动与配置方法见[前端对接](frontend-integration.md)。
