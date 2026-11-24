[English](../releases.md) · [简体中文](releases.md)

# 版本发布与 npm 安装

## 启动桌面应用

安装 Node.js 24 LTS、Python 3.12 和 Bash 后运行：

```bash
npx vera-harness
```

启动器支持 Node.js 22–25、Python 3.10–3.13。Windows 使用 Git for Windows Bash。
首次启动下载 Electron，将包内 VERA wheel 和 Python 依赖安装到独立虚拟环境。
经过认证、仅监听本机回环地址的服务就绪后，桌面窗口才会打开。关闭应用时停止该服务。
提交任务前，在桌面设置中配置模型。

长期安装可用 `npm install -g vera-harness`，之后运行 `vera-harness`。
`npx` 执行的是同一个 npm 包，不需要单独发布。本次为 Alpha 版本，Windows 和 Linux 运行 CI。
macOS 与签名原生安装包不在本次已验证的分发范围内。

## 配置与恢复

| 设置或命令 | 用途 |
| --- | --- |
| `VERA_PYTHON` | Python 可执行文件路径，不附加参数。 |
| `VERA_RUNTIME_DIR` | 各版本独立运行环境的上级目录。 |
| `vera-harness --doctor` | 检查 Python 是否可用，并校验包内 wheel。 |
| `vera-harness --setup-only` | 准备运行环境，不打开窗口。 |
| `vera-harness --version` | 输出 npm 桌面版本号。 |

Windows 环境缓存位于 `%LOCALAPPDATA%/VERA/runtimes`；其他系统使用
`$XDG_CACHE_HOME/vera-harness/runtimes` 或 `~/.cache/vera-harness/runtimes`。
不同包版本、不同 wheel 校验值使用独立环境，不修改系统 Python。
安装失败时不会写入就绪标记，重新启动可继续安装。若安装中断后留下锁，
先确认没有其他 VERA 安装进程，再移除提示中的 `.setup-lock` 目录。
[配置与历史](storage.md)不放在运行环境缓存中。

## 构建与发布

在仓库根目录使用项目 Python 环境运行：

```bash
python -m pip install build twine
npm --prefix desktop ci
npm --prefix desktop run build
python scripts/build_desktop_package.py
npm pack ./dist/npm --pack-destination ./dist
node dist/npm/bin/vera-harness.mjs --doctor
node --test tests/launcher/runtime.test.mjs
```

包中包含桌面前端构建、`source/` 下的对应前端源码与补丁、许可证、VERA wheel 和 SHA-256 校验值，
不包含宣传落地页源码、本机配置与凭据。`dist/` 不纳入 Git。npm 版本 `0.1.0-alpha.2` 对应
Python 版本 `0.1.0a2` 与标签 `v0.1.0-alpha.2`。

从 `main` 创建临时分支准备发布候选，全部 10 项必需 CI 检查通过后，经 PR 合入受保护的 `main`。
单维护者策略的人工批准数为 0，交付后删除临时分支。
给已合入 `main` 的提交打标签，创建 Alpha GitHub Release，附上已审查的 npm 压缩包、Python wheel 与校验文件。
GitHub 同时提供标签对应的源码归档，Release 工作流也会从标签重建并上传产物。

使用已获授权的 npm 账号发布已审查的包：

```bash
npm whoami --registry=https://registry.npmjs.org/
npm publish ./dist/vera-harness-0.1.0-alpha.2.tgz --access public --tag latest --registry=https://registry.npmjs.org/
npm view vera-harness version --registry=https://registry.npmjs.org/
```

发布的 Alpha 作为 npm 默认版本，用户直接运行 `npx vera-harness` 即可使用，版本号仍明确标注 Alpha。
在本机完成浏览器授权或双因素确认，不提交 npm 凭据。工作流不发布 PyPI，也不保存 npm token。
发布后核实全新 npm 安装，并记录最终提交与产物校验值。
