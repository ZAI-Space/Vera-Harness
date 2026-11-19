# 后端对接边界

完整的中英双语接口说明已合入主项目，避免维护两套过期契约：

- [中文接口与运行边界](../../docs/zh/frontend-integration.md)
- [English backend integration](../../docs/frontend-integration.md)
- [中文流式呈现](../../docs/zh/desktop-streaming.md)
- [English streaming presentation](../../docs/desktop-streaming.md)

`src/contracts` 为 TypeScript 契约；`src/main/services/http-transport.ts` 负责认证的本机 HTTP 连接；`../../src/vera/desktop` 为 Python 实现。桌面主进程不导入执行 SDK，后端生命周期由仓库根目录启动器管理。
