[English](../windows.md) · [简体中文](windows.md)

# Windows 与 Bash 启动

!!! abstract "跨平台命令环境"

    需要预先安装 Python 3.10 或更高版本。Windows 本地工具调用 Git for Windows Bash，Linux 使用现有 Shell。Git Bash 提供命令环境，不是 Linux 虚拟机；从 Bash 启动 Python 也不会自动改变 Windows subprocess 的默认 Shell。

## 两种启动入口

PowerShell/CMD 在仓库运行 `.\start.cmd`；Git Bash/Linux 运行 `bash scripts/start.sh`。参数和调用方工作目录会保留。首次创建 `.venv` 并安装当前源码，后续复用；Windows 解释器在 `.venv/Scripts/python.exe`，Linux 在 `.venv/bin/python`。激活环境后可直接运行 `vera`。

## Bash 检测和缺失处理

按 `VERA_BASH_PATH`、用户缓存、PATH 上的 Git、注册表和常见安装位置查找，不将 Windows 系统 Bash/WSL 启动器当成 Git Bash。找不到时，仓库启动器从官方 Git for Windows Release 下载完整 PortableGit，核对发布的 SHA256，再解压到用户缓存。无需管理员权限，不修改系统 PATH。下载或校验失败就停止，绝不执行未验证文件。

新安装缓存位于 `%LOCALAPPDATA%/VERA/git`；新缓存不存在且旧 `%LOCALAPPDATA%/mini-swe-agent/git` 已存在时，复用旧安装。离线首次使用需手动安装或准备完整便携 Git，并设置 `VERA_BASH_PATH`。库调用 `LocalEnvironment` 只检测，不自动下载。已经处于 Git Bash 中时复用当前 Git 安装；Linux 不下载 PortableGit。

## 命令执行和终端

Windows 显式传入 `--noprofile --norc -c`，每条操作使用新 Shell。Mintty 在原生 Python 不能识别终端时使用 winpty；Windows Terminal 可直接承载。支持重定向帮助和非交互调用。路径尽量使用正斜杠并正确引用，有需要时用 cygpath，不全局禁用 MSYS2 路径转换。

超时通过受管进程树终止和有界输出读取处理。这里是本地权限执行，不是沙箱。Linux 容器后端、镜像和命名空间需单独验证。历史平台验证不代表当前所有可选环境通过；按文末命令重测当前候选。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```powershell
.\start.cmd --help
.\start.cmd -m YOUR_PROVIDER/YOUR_MODEL
```

```bash
bash scripts/start.sh --help
bash scripts/start.sh -m YOUR_PROVIDER/YOUR_MODEL
```

```powershell
$env:VERA_BASH_PATH = 'D:\Tools\Git\bin\bash.exe'
.\start.cmd
```

```powershell
.venv\Scripts\python -m pytest tests/environments/test_local.py tests/environments/test_windows_local.py tests/agents/test_default.py tests/agents/test_interactive.py tests/config tests/test_init.py tests/run/test_windows_startup.py tests/utils -q
```
