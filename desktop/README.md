[English](README.en.md) · [简体中文](README.md)

# VERA Desktop

Electron + React 桌面入口，与终端共享 VERA Python Runtime。

从仓库根目录安装 Python 依赖后，在此目录执行 `npm ci`。推荐 Node.js 24 LTS。

```powershell
# 在仓库根目录启动；同时管理本机后端和桌面窗口
powershell -File scripts/start-desktop.ps1
```

Git Bash、Linux/macOS：`bash scripts/start-desktop.sh`。Windows 使用 Git Bash 执行本地工具命令。无需 Docker；配置好的沙箱可独立选择。

仅开发界面时可执行 `npm run dev`；未指定后端连接文件时为明确标注的预览，不能执行智能体任务。

检查：`npm run check:boundary`、`npm run lint`、`npm run typecheck`、`npm test`、`npm run build`。跨语言集成测试需根目录 `.venv`，或通过 `VERA_PYTHON` 指定已安装 VERA 的 Python。

[后端接口与运行边界](../docs/zh/frontend-integration.md) · [流式与思考呈现](../docs/zh/desktop-streaming.md)

前端来源及许可证见 [Percho MIT](third_party/percho-LICENSE) 与 [PI-Desktop LGPL-3.0](third_party/pi-desktop/NOTICE.md)。这些声明保留各自代码的许可，不将 LGPL 部分改为 MIT。
