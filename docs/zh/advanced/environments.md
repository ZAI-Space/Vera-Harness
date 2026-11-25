[English](../../advanced/environments.md) · [简体中文](environments.md)

# 执行环境

Environment 执行命令，SandboxConfig 追加隔离、挂载与外部能力策略。低层 environment_class 与具名沙箱不是同一配置入口。

| 名称 | 环境与依赖 |
| --- | --- |
| local | 宿主执行，Windows 使用 Git Bash，无隔离 |
| docker | Docker/Podman，要求运行引擎和兼容镜像 |
| bubblewrap | Linux 命名空间，需要可用 user namespace |
| singularity | Singularity/Apptainer 与对应镜像 |
| swerex_docker | SWE-ReX 依赖和容器引擎 |
| swerex_modal | Modal 服务、认证、依赖与网络 |
| contree | 兼容 ConTree SDK 和服务权限 |

通过 `--environment-class` 或 `environment.environment_class` 选择后端，通过 `--sandbox` 或 `--sandbox-profile` 配置隔离策略。运行前安装所选后端的依赖。配置方法、工作区边界和可用状态见[沙箱](../sandbox.md)。

## 配置、命令与源码示例

```bash
vera --environment-class local
vera --sandbox docker
vera --sandbox-profile python-dev
```
