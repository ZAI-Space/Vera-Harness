[English](../sandbox.md) · [简体中文](sandbox.md)

# 工作区沙箱

!!! abstract "用户配置，按任务选择"

    沙箱引擎与镜像由用户安装和配置，不会因为检测到 Docker 就自动生成环境，也不会从选择器强制下载。没有沙箱可继续本地运行；没有可用具名配置时前端禁用选择器，展示原因。

## 具名环境

通过 `sandboxes save/list/check/remove` 保存稳定的 docker 或 bubblewrap 后端。显式 replace 才能覆盖，数据存储在全局配置下的 sandbox-profiles.sqlite3，设置可选独立库路径。引擎离线也可保存配置；检查需要实际工作区、引擎、现有镜像或可用命名空间，不创建容器以探测可用性。

终端 `/sandbox NAME` 或 CLI `--sandbox-profile` 选择，`/sandbox none` 显式本地。与 `--sandbox` 同时使用会被拒绝。当前项目在选择时绑定；直接 Python Runtime 可由 sandbox.workspace 或 environment.cwd 指定。配置整份替换，不把上个沙箱选项残留到新环境。父与 Subagent 共享选择和工作区边界，任务中途修改作用于下一任务。

## 后端与权限

auto 在 Linux/WSL 优先探测 Bubblewrap，再探测有镜像的本地 Linux Docker；不可用就解释失败，不静默本地执行。Docker 需运行中的 Linux 引擎，默认镜像 python:3.12-slim；Bubblewrap 需 Linux/WSL 和可用 user namespace。local 具有宿主用户权限。显式后端不可用时启动失败。

隔离模式把工作区挂载到 /workspace，支持只读/读写、临时目录，默认禁用 Shell 网络。Docker 还限制 CPU、内存、进程数并在命令超时清理容器。模型请求仍来自宿主端。stdio MCP 在宿主进程、远程 MCP 和网页服务必须显式可信 opt-in，不能把它们误认为也被 Shell 沙箱隔离。

## 前端接口

`SandboxProfiles` 管理设置并返回 available/code/reason；空库只读不创建文件、不探测所有安装程序。`TerminalSession.sandbox_status/select_sandbox/set_mode/runtime_config` 提供设置与选择，校验失败不修改选择。可用性是快照，实际启动会重查。权限模式独立于环境，配置和调用示例见下方。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```yaml
mode: docker
docker_image: python:3.12-slim
workspace_access: read-write
timeout: 30
```

```bash
vera-extra sandboxes save python-dev python-sandbox.yaml
vera-extra sandboxes list
vera-extra sandboxes check --workspace .
vera-extra sandboxes save python-dev python-sandbox.yaml --replace
vera-extra sandboxes remove python-dev
```

```json
{
  "configured": false,
  "enabled": false,
  "reason": "Configure a sandbox in settings first.",
  "choices": [],
  "selected": null
}
```

```bash
vera --sandbox auto
vera --sandbox bubblewrap
vera --sandbox docker
vera --sandbox local
```

```yaml
sandbox:
  mode: auto
  workspace: .
  workspace_access: read-only
  timeout: 30
```

```yaml
sandbox:
  mode: docker
  host_mcp_servers: [local-docs]
  remote_mcp_servers: [approved-api]
  allow_web_tools: true
```
