[English](../../models/local_models.md) · [简体中文](local_models.md)

# 本地模型

!!! abstract "连接地址与费用独立配置"

    配置本地 OpenAI-compatible 服务的 api_base、provider/model、认证和真实工具支持；服务可连接不表示命名工具有效。模型请求来自 VERA 宿主进程，不在 Shell 沙箱内。

## 请求与记账

使用 YAML model_kwargs 指定地址并叠加到完整基础配置。原生工具模型才支持网页、MCP、plan 等能力；仅文本接口请选择文本动作适配器并接受 Bash 范围。

未知模型价格通过 model.litellm_model_registry 或对应 registry 环境变量指定 JSON。下面零价仅在操作者确认真实记账价为零时适用；否则填写实际每 token 价格，并核对供应商 usage。ignore_errors 可以抑制价格缺失错误，但费用可能低报，不是消费限额。

Portkey 可用 litellm_model_name_override 让网关模型名对应价格标识。模型服务安装、硬件容量、价格和账号开通不由 VERA 启动器承担。实际字段以[当前 Config API](../reference/models/overview.md)为准。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```yaml
model:
  model_class: litellm
  model_name: openai/local-model
  model_kwargs:
    api_base: http://127.0.0.1:8000/v1
```

```bash
vera -c vera.yaml -c local-model.yaml
```

```json
{
  "openai/local-model": {
    "input_cost_per_token": 0.0,
    "output_cost_per_token": 0.0,
    "max_tokens": 8192,
    "litellm_provider": "openai",
    "mode": "chat"
  }
}
```
