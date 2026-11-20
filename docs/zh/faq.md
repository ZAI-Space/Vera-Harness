[English](../faq.md) · [简体中文](faq.md)

# 常见问题

!!! question "Windows、Linux 都可以运行吗？"

    可以。Windows 本地命令使用 Git Bash，Linux 使用配置的 Shell。容器、Bubblewrap 等可选后端有各自依赖，不能因为类可导入就视为可用。见[启动](windows.md)和[沙箱](sandbox.md)。

??? question "一定需要 Docker 吗？"

    不需要。local 使用当前用户的宿主机权限。沙箱由用户配置，显式请求的后端不可用时失败，不自动降级，也不因选择命令下载引擎或镜像。

??? question "只有 Bash 工具吗？"

    不是。除了 Bash 文件与构建操作，还支持网页工具、MCP、Skill、插件和 Subagent。命名工具要求原生工具调用模型；文本动作模型仍走 Bash 路径。

??? question "权限、模式和沙箱有何区别？"

    `confirm / yolo / human` 决定审批和操作来源；`/plan` 只读调研并保存计划；`/goal` 在预算内持续推进目标；沙箱决定命令隔离环境。几者不会隐式相互切换。

??? question "配置和 Shell 状态在哪里？"

    启动打印全局 `.env` 路径，`VERA_GLOBAL_CONFIG_DIR` 可以覆盖。环境变量优先，旧目录与变量名保留兼容。每条 Bash 是新进程，前一条的 cd/export 不会保留；配置 cwd/env 或在每条命令中显式指定。

??? question "定时任务会无限运行吗？本地测试证明模型效果吗？"

    目标有轮次、费用和时间预算，定时任务有单次限额；检查发生在调用边界，已发出请求可能超支。后台调度需要服务持续运行，不能唤醒关机电脑。协议测试、真实沙箱、付费模型和任务评测是不同证据，必须注明版本与未验证范围。

??? question "前端接口全部完成了吗？"

    已完成。桌面适配器通过带认证的本机回环传输连接 Python 服务。支持的方法和校验边界见[前端对接](frontend-integration.md)；可选供应商和沙箱仍取决于本机环境。
