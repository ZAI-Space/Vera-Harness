[English](../taskboard.md) · [简体中文](taskboard.md)

# 任务看板集成

VERA 可打开单独安装的 dashi-taskboard，并通过桌面对话执行选定任务。上游应用是可选依赖，不随本仓库打包。

## 安装与打开

Windows 用户先阅读并在仓库根目录运行 `scripts/setup-taskboard.ps1`。脚本检出固定版本 `bc25451c5c49a14abb6c4e8250b62c626b007f8a`，安装及构建上游应用，保留许可证，并在 VERA 配置目录记录安装位置。需要 Git、Node、npm 和网络；不会执行上游的 Codex 注入或安装脚本。

打开桌面任务看板页才会启动所管理的服务。缺少安装或 Node 时显示前置条件。`VERA_TASKBOARD_HOME` 可指定已有构建目录；使用此覆盖项时，所有者负责确认该目录的来源。

## 执行任务

执行前选择项目、模型和权限。适配器核对任务标识、版本及当前状态，再创建独立执行对话。在对话中查看流式输出并处理审批。

运行完成后进入待审核状态，不自动验收任务。停止看板服务前，先停止正在执行的对话。关闭服务不会清除桌面配置目录内的任务数据。

## 服务边界

适配器为上游服务设置 `127.0.0.1`、随机实例 token、独立 secret 和私有数据目录。桌面通过带 sandbox 的 iframe 显示看板；能力链接应保持私有。完整路由控制由实际安装的上游版本负责，与 VERA 本机 `/invoke` 认证是两条边界。

集成测试位于 `tests/run/test_taskboard_integration.py` 和 `test_taskboard_execution.py`，运行前需安装任务面板。
