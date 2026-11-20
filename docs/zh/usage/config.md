[English](../../usage/config.md) · [简体中文](config.md)

# 配置命令

config setup 启动交互向导，询问默认模型及可选 API 变量和值；首次运行可自动进入向导。set 修改键，未给键/值则询问；unset 删除；edit 用 EDITOR 或 nano 打开全局私有 .env。

密钥避免写在命令参数或公开 YAML 中，编辑器内容也不能直接截图分享。环境变量优先级与额外设置见[全局配置](../advanced/global_configuration.md)。下面示例使用占位模型与非敏感默认模型键。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
vera-extra config setup
```

```bash
# example: set default model
vera-extra config set VERA_MODEL_NAME anthropic/claude-sonnet-4-5-20250929
# or interactively
vera-extra config set
```

```bash
vera-extra config unset VERA_MODEL_NAME
```

```bash
vera-extra config edit
```

```python
--8<-- "src/vera/run/utilities/config.py"
```
