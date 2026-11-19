[English](../contributing.md) · [简体中文](contributing.md)

# 参与开发

!!! abstract "正确、可读、一致、简洁"

    先读实现、调用方和测试，优先复用 Runtime 与现有模块。UI 与可选服务不进入基础循环。一次改动聚焦单一目的，保持可追溯。

## 本地开发与分支

安装 full/channels 开发依赖，执行 Ruff 格式/检查、相关测试、构建、严格文档构建及双语检查。新集成测试使用真实文件、子进程和显式本地协议服务；缺失依赖和付费验证分别记录。

日常从 dev 拉 `<type>/-<kebab-case>` 分支，经 PR 合回 dev；main 用于发布/hotfix/生产回滚。提交使用约定格式，合并前同步目标并重跑相关检查。日常 Squash，dev→main 发布采用 Merge Commit；实际评审与保护按当前协作规则执行。

## 文档

行为变化同步英中页面，保留 Markdown 标题、提示块、表格、可运行代码和 API 引用。技术标识按源码，不为了语言翻译字段。凭据和虚构验证结果禁止写入。逐页核对地图见[文档维护](documentation.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
python -m pip install -e '.[full,channels]'
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -n 2 -ra
python -m build
python -m mkdocs build --strict
python scripts/check_docs.py
```
