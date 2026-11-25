[English](../contributing.md) · [简体中文](contributing.md)

# 参与开发

!!! abstract "正确、可读、一致、简洁"

    先读实现、调用方和测试，优先复用 Runtime 与现有模块。UI 与可选服务不进入基础循环。一次改动聚焦单一目的，保持可追溯。

## 本地开发与分支

安装 full/channels 开发依赖，执行 Ruff 格式检查、相关测试、构建及双语文档检查。集成测试使用真实文件、子进程和本地协议服务。环境与命令见[测试文档](testing.md)。

`main` 是唯一长期、默认和生产分支。从 `main` 创建 `<type>/-<kebab-case>` 临时任务分支，经 PR 合回 `main`。提交使用约定格式，合并前同步目标并重跑相关检查。日常与 hotfix PR 使用 Squash Merge。发布时给已合入 `main` 的提交打标签，交付后删除临时分支。

保留 `main` 分支保护。单维护者策略要求通过 PR 和全部 10 项必需 CI 检查，人工批准数为 0。

## 文档

行为变化同步英中页面，保留 Markdown 标题、提示块、表格、可运行代码和 API 引用。配置字段与标识符保持源码写法，示例凭据使用占位符。维护方法见[文档维护](documentation.md)。

## 配置、命令与源码示例

```bash
python -m pip install -e '.[full,channels]' build twine
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python -m build
python -m mkdocs build --strict
python scripts/check_docs.py
```
