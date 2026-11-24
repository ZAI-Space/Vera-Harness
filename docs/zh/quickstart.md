[English](../quickstart.md) · [简体中文](quickstart.md)

# 快速开始

!!! abstract "运行条件"

    Python 3.10 及以上、用于克隆的 Git，以及执行本地命令所需的 Bash。Windows 使用 Git for Windows Bash。查看帮助不调用模型；执行真实任务需要模型及其供应商凭据。

## 从源码安装

克隆当前 VERA 仓库，创建 `.venv`。PowerShell 使用 `.venv/Scripts/Activate.ps1`，Git Bash 使用 `source .venv/Scripts/activate`，Linux 使用 `source .venv/bin/activate`。下面保留三种终端的完整命令。推荐安装 `.[mcp,channels]`；基础运行可用 `pip install -e .`，开发使用 `.[dev]` 或 `.[full,channels]`。

文档以当前仓库为安装来源，不承诺同名公共 PyPI 包已经发布。已有用户更新当前虚拟环境中的源码安装即可；配置目录与历史数据不会因品牌更新自动迁移。

## 配置模型并提交任务

运行 `vera-extra config setup`，按提示填写 provider/model 和凭据，再启动 `vera`。敏感值优先使用交互输入或环境变量，不写进命令行历史、公开 YAML 或 Git。供应商模型名称及访问权限需按实际账号核对。

在输入框使用 `@文件`、`/skill`、`/mcp`，Tab 补全，Esc 后 Enter 提交多行内容。`/plan` 先生成方案，`/goal` 在预算内继续完成目标。`confirm` 询问操作，`yolo` 不逐项审批，`human` 执行用户输入的命令；权限模式不会自动创建沙箱。

## 启动脚本与兼容入口

PowerShell/CMD 用 `.\start.cmd`，Git Bash/Linux 用 `bash scripts/start.sh`。脚本准备项目虚拟环境；Windows 缺少 Bash 时可下载并验证 PortableGit，沙箱引擎仍由用户配置。新入口为 `vera`、`vera-extra`、`python -m vera`，旧 `mini` 入口继续有效。

详见[模型配置](models/quickstart.md)、[终端](terminal.md)、[启动说明](windows.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
git clone --branch main https://github.com/ZAI-Space/Vera-Harness.git
cd Vera-Harness
python -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[mcp,channels]'
vera --help
```

```bash
source .venv/Scripts/activate
python -m pip install -e '.[mcp,channels]'
vera --help
```

```bash
source .venv/bin/activate
python -m pip install -e '.[mcp,channels]'
vera --help
```

```bash
vera-extra config setup
vera
```

```text
Explain @src/main.py
/skill
/mcp
/plan Add a regression test for this module
/goal Fix the failing tests and show the verification output
```

```bash
vera-extra --help
python -m vera --help
```
