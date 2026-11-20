[English](../repository-structure.md) · [简体中文](repository-structure.md)

# 仓库目录结构

VERA 使用小型 monorepo 结构：一个 Python 源码包和一个桌面应用。源码、
测试、示例、文档和生成物分别归属明确目录。

| 路径 | 归属 | 内容 |
| --- | --- | --- |
| `src/vera/` | Python 源码 | Runtime、Agent、模型、工具、记忆、渠道和 CLI 模块 |
| `desktop/` | 桌面源码 | Electron 主进程、preload、渲染器、契约和桌面测试 |
| `tests/` | Python 验证 | 单元、集成、系统测试和少量夹具 |
| `examples/` | 对外示例 | 安全的插件、Skill、MCP 和配置示例 |
| `docs/` | 产品文档 | 中英文教程、操作指南、参考和架构说明 |
| `scripts/` | 维护脚本 | 可移植启动、文档、边界和验证脚本 |
| `.github/` | 仓库自动化 | CI、Issue 表单和 Pull Request 模板 |
| `site/`、`dist/`、`.venv/`、`node_modules/`、`desktop/out/` | 生成/本地目录 | 不提交，由锁文件和构建命令重新生成 |

根目录只放项目入口和仓库治理文件：README 双版、许可证和版权声明、包元数据、
Git 配置、启动入口以及贡献者/Agent 说明。功能说明放在 `docs/`，可运行的公开示例
放在 `examples/`，验证夹具放在 `tests/`。

仓库不保留阶段计划、临时验收报告、截图、本地日志或复制的构建产物。可复用的验证
流程写入测试，稳定的产品事实写入对应的中英文文档。
