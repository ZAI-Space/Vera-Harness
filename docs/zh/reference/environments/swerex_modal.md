[English](../../../reference/environments/swerex_modal.md) · [简体中文](swerex_modal.md)

# SWE-ReX Modal

!!! abstract "API 参考"

    本页展示 VERA 当前源码生成的接口。标识符、类型签名和源码注释保持源语言，中文说明不改动调用契约。先确认组件配置及依赖，再按接口传参。

环境负责命令执行和资源生命周期。所需引擎/SDK/凭据须实际准备；本地权限与沙箱隔离是不同边界。详情见[环境](../../advanced/environments.md)。

## 配置、命令与源码示例

```bash
python -m pip install -e '.[full]'
```

```bash
modal setup
```

```
vera-extra swebench \
    --config src/vera/config/benchmarks/swebench_modal.yaml \
    --subset verified \
    --split test \
    --workers 1 \
    -o ./results/gpt5-mini-modal
```
