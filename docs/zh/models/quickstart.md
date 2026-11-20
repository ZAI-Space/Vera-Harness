[English](../../models/quickstart.md) · [简体中文](quickstart.md)

# 模型配置

!!! abstract "区分适配器和供应商"

    model_class 选择适配器，model_name 选择 provider/model。默认 LiteLLM，命名工具、MCP、plan/goal 要求原生工具调用。供应商可用模型、价格与参数持续变化，不使用冻结旧清单作为当前事实。

## 凭据和配置

通过 setup 交互配置，或用对应供应商环境变量，如 OPENAI_API_KEY、ANTHROPIC_API_KEY、GEMINI_API_KEY、OPENROUTER_API_KEY、PORTKEY_API_KEY、REQUESTY_API_KEY。-m 可显式指定模型。下面示例仅为占位，不表示账号必然有访问权限。

YAML 的 model 包含 model_class、model_name 和 model_kwargs；后者透传参数，按供应商支持设置 max_tokens/timeout 等。传 -c 时包含完整基础配置再叠加覆盖文件。Anthropic 类名称在没有显式设置时使用既有缓存配置。

## 适配器

litellm、litellm_response 分别对应 Chat/Responses；openrouter、openrouter_response、portkey、portkey_response、requesty 采用各自网关。litellm_textbased/openrouter_textbased 为 Bash 文本动作，不能提供命名能力。deterministic 为预设输出测试，不调用供应商。正确 Responses 短名是 litellm_response。每个注册表使用独立模型实例，自定义适配器可以给完整类路径。

本地 OpenAI-compatible 服务需配置实际 api_base、认证和工具能力，价格缺失时配置 registry，不把忽略记账错误当作免费。见[本地模型](local_models.md)、[排错](troubleshooting.md)及[API](../reference/models/overview.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
vera-extra config setup
vera-extra config set VERA_MODEL_NAME openai/YOUR_MODEL
vera -m openai/YOUR_MODEL
```

```yaml
model:
  model_class: litellm
  model_name: openai/YOUR_MODEL
  model_kwargs:
    max_tokens: 4096
    timeout: 60
```

```bash
vera -c vera.yaml -c model.yaml
```

```yaml
model:
  model_class: litellm
  model_name: openai/local-model
  model_kwargs:
    api_base: http://127.0.0.1:8000/v1
```
