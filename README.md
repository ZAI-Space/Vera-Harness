<div align="center">
  <img src="docs/assets/vera-logo.png" alt="VERA Logo" width="200" />
  <h1>VERA</h1>
  <p><strong>从终端到桌面，围绕任务组装 Agent 能力。</strong></p>
  <p>模型 · 工具 · 记忆 · 委派 · 隔离 · 持续目标</p>
  <p>
    <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square" />
    <img alt="Windows and Linux" src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-008C95?style=flat-square" />
    <a href="LICENSE.md"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-6F42C1?style=flat-square" /></a>
  </p>
  <p><strong>简体中文</strong> · <a href="README.en.md">English</a></p>
  <p><a href="docs/zh/quickstart.md">快速开始</a> · <a href="docs/zh/index.md">文档</a> · <a href="docs/zh/frontend-integration.md">前端对接</a> · <a href="https://github.com/zml-mis/Vera-Harness/issues">反馈</a></p>
</div>

---

VERA 是模块化的 Agent Harness。终端、渠道与定时任务复用同一套 Python Runtime；模型、工具、记忆、Subagent 和执行环境按任务组合，状态观察与外部控制器围绕基础循环扩展。

## 能力一览

| 任务需要 | VERA 提供 |
| --- | --- |
| 理解项目 | `@` 搜索并添加项目文件，Skill 按需加载 |
| 操作与检索 | Bash、网页搜索/提取、MCP 服务与统一工具注册表 |
| 按角色委派 | 自定义 Subagent 的模型、工具、技能、行为和预算 |
| 跨会话记忆 | Hindsight 项目/共享 bank 与有界上下文投影 |
| 扩展工作流 | GitHub / Gitee 插件市场、MCP Registry、skills.sh |
| 控制执行 | `confirm` / `yolo` / `human`，用户配置的 Docker/Bubblewrap 沙箱 |
| 持续推进 | `/plan` 只读规划、`/goal` 有预算的目标闭环、独立定时任务 |
| 检查与恢复 | 生命周期事件、SQLite 收据、轨迹、核对后恢复 |
| 远程使用 | 微信扫码、飞书应用机器人长连接 |
| 版本化改进 | 外部评测与源码演化，候选版本独立于生产分支 |

## 开始使用

需要 Python 3.10+；Windows 本地执行使用 Git Bash，Linux 使用 Bash。先从源码安装：

```bash
git clone --branch dev https://github.com/zml-mis/Vera-Harness.git
cd Vera-Harness
python -m venv .venv
```

激活虚拟环境：PowerShell 用 `.\.venv\Scripts\Activate.ps1`，Git Bash 用 `source .venv/Scripts/activate`，Linux 用 `source .venv/bin/activate`。随后：

```bash
python -m pip install -e '.[mcp,channels]'
vera-extra config setup
vera
```

仓库启动器也可直接使用：PowerShell/CMD 运行 `.\start.cmd`，Git Bash/Linux 运行 `bash scripts/start.sh`。启动器可准备虚拟环境，Windows 缺少 Bash 时核验并准备 PortableGit；沙箱引擎和镜像由用户配置。模型任务需要真实模型配置和凭据，帮助命令不需要。

## 在终端中

```text
检查 @src/main.py，并给出实际验证结果
/skill
/mcp
/subagent
/sandbox
/plan 为当前项目设计测试补全方案
/goal 完成测试补全并确保相关检查通过
/goal status
```

Tab 选择候选，Esc 后 Enter 提交多行输入。权限、运行模式与沙箱分别选择：`human` 是手动命令，`yolo` 不逐项审批；`/plan` 不实施代码，`/goal` 不自动扩大权限。没有可用沙箱时继续使用显式本地执行。

## 文档与集成

- [中文文档](docs/zh/index.md) / [English documentation](docs/index.md)：两版页面互相链接。
- [前端对接](docs/zh/frontend-integration.md)：会话、状态、能力选择、审批与存储边界。已有 Python 接口；桌面传输层和真实 UI 联调需要另行完成。
- [命名迁移](docs/zh/advanced/v2_migration.md)：正式命名为 `vera`、`VERA_*` 和 `vera.yaml`，说明历史配置的兼容读取范围。
- [文档维护](docs/zh/documentation.md)：逐页检查清单与过期内容修订。

## 开发与验证

```bash
python -m pip install -e '.[full,channels]'
python -m ruff check src tests
python -m ruff format --check src tests
python -m pytest -n 2 -ra
python scripts/check_docs.py
python -m mkdocs build --strict
```

日常分支从 `dev` 创建，经 PR 合回 `dev`；发布再进入 `main`。可选服务缺失、真实模型费用及人工平台联调应分别报告，不把跳过项或上游分数当作当前 VERA 验证结果。

## 许可与来源

采用 [MIT](LICENSE.md) 许可。源码来源和第三方版权保留于 [Third-party notices](THIRD_PARTY_NOTICES.md)；产品品牌更名不移除这些权利说明。
