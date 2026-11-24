[English](../repository-structure.md) · [简体中文](repository-structure.md)

# 仓库结构

本仓库包含 VERA Runtime、终端和桌面适配器、测试、示例与技术文档。每个文件应放在负责其行为的目录中。

| 路径 | 内容 | 提交规则 |
| --- | --- | --- |
| `src/vera/` | Python Runtime、模型、Agent、工具、环境、存储、渠道和适配器 | 提交源码和维护中的包数据。 |
| `desktop/src/` | Electron 主进程、preload 桥、契约和 React renderer | 提交源码；正式测试放在 `desktop/tests/`；renderer 不直接导入 Python Agent SDK。 |
| `tests/` | Python 单元、集成和本地协议测试 | 维护中的测试统一放在这里；跨模块和进程测试放在 `tests/run/`。 |
| `desktop/tests/` | 前端单元和组件测试 | 镜像被测源码路径；UI 验收位于 `desktop/tests/ui/`。 |
| `examples/` | 小型、安全的插件和配置示例 | 使用占位凭据与本地路径，不调用付费服务。 |
| `docs/` 与 `docs/zh/` | 成对的英文和中文用户、开发者文档 | 行为变化同时更新两种语言，保留准确命令和标识符。 |
| `website/` | 静态落地页源码 | 将共用文档构建到 `website/docs/`，仅提交源码。见[官网文档接入](website.md)。 |
| `desktop/third_party/` 与 `THIRD_PARTY_NOTICES.md` | 复用代码和依赖的来源、许可证说明 | 随发布源码保留声明。 |
| `scripts/` | 仓库维护和启动脚本 | 不写入凭据或仓库内报告。 |

## 生成文件和本地文件

不要提交 `.venv/`、Python 缓存、覆盖率输出、`desktop/node_modules/`、`desktop/out/`、`desktop/.local/`、`desktop/coverage/`、`site/`、`website/docs/`、本地轨迹、日志、报告和凭据。桌面 UI 验收结果写入临时目录，验收驱动和确定性夹具仍属于仓库源码。

## 命名和职责

Python 模块和函数使用 `snake_case`，React 组件使用 `PascalCase`，TypeScript 函数和 store 沿用 `camelCase`。一个文件只负责一个主题；文件接近 1,000 行或包含无关职责时拆分模块。

Python API 名称和公开技术文档使用英文。属于产品界面的中文注释和双语文档可以保持现有语言。注释必须描述当前行为，停用代码直接删除。

## 交付前检查

在仓库根目录运行：

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

在 `desktop/` 目录运行：

```bash
npm run check:boundary
npm run lint
npm run typecheck
npm test
npm run build
npm run test:ui
```

缺失的可选服务、付费模型运行和人工验收分别记录。确定性本地夹具只证明夹具路径，不代表真实服务质量。
