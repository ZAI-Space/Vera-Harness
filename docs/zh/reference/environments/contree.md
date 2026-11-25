[English](../../../reference/environments/contree.md) · [简体中文](contree.md)

# ConTree

!!! abstract "API 参考"

    本页展示 VERA 当前源码生成的接口。标识符、类型签名和源码注释保持源语言，中文说明不改动调用契约。先确认组件配置及依赖，再按接口传参。

环境负责命令执行和资源生命周期。所需引擎/SDK/凭据须实际准备；本地权限与沙箱隔离是不同边界。详情见[环境](../../advanced/environments.md)。

::: vera.environments.extra.contree

## 配置、命令与源码示例

```python
--8<-- "src/vera/environments/extra/contree.py"
```

```bash
python -m pip install -e '.[contree]'
```

```bash
export CONTREE_TOKEN="your-contree-token"
export CONTREE_BASE_URL="your-given-base-url-for-contree"
```

```
vera-extra swebench \
    --subset verified \
    --split test \
    --workers 1 \
    --environment-class contree
```
