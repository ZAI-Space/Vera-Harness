[English](../../../reference/environments/singularity.md) · [简体中文](singularity.md)

# Singularity

!!! abstract "API 参考"

    本页展示 VERA 当前源码生成的接口。标识符、类型签名和源码注释保持源语言，中文说明不改动调用契约。先确认组件配置及依赖，再按接口传参。

环境负责命令执行和资源生命周期。所需引擎/SDK/凭据须实际准备；本地权限与沙箱隔离是不同边界。详情见[环境](../../advanced/environments.md)。

::: vera.environments.singularity

## 配置、命令与源码示例

```python
--8<-- "src/vera/environments/singularity.py"
```
