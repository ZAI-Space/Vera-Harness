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

可通过 --environment-class 或 environment.environment_class 选择，隔离策略通过 --sandbox/--sandbox-profile。可导入类不代表服务可用；原生 Windows 本地测试也不证明 Linux 容器可用。实际设置、工作区边界及无环境的灰态处理见[沙箱](../sandbox.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
vera --environment-class local
vera --sandbox docker
vera --sandbox-profile python-dev
```
