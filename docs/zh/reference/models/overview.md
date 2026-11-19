[English](../../../reference/models/overview.md) · [简体中文](overview.md)

# Models Overview

!!! abstract "API 参考"

    本页展示 VERA 当前源码生成的接口。标识符、类型签名和源码注释保持源语言，中文说明不改动调用契约。先确认组件配置及依赖，再按接口传参。

模型适配器负责请求、动作解析、观察消息和费用。原生工具与文本动作的能力不同；接口存在不代表供应商账号/模型已经开通。详情见[模型配置](../../models/quickstart.md)。

## 模型类

| 类 | 短名 | 端点 | 原生工具调用 | 用途 |
| --- | --- | --- | --- | --- |
| [`LitellmModel`](litellm.md) | `litellm` | `/chat/completions` | 是 | 默认 LiteLLM 供应商适配 |
| [`LitellmTextbasedModel`](litellm.md) | `litellm_textbased` | `/chat/completions` | 否 | 从文本解析 Bash 动作 |
| [`LitellmResponseModel`](litellm_response.md) | `litellm_response` | `/responses` | 是 | LiteLLM Responses 适配 |
| [`OpenRouterModel`](openrouter.md) | `openrouter` | `/chat/completions` | 是 | OpenRouter Chat Completions |
| [`OpenRouterTextbasedModel`](openrouter.md) | `openrouter_textbased` | `/chat/completions` | 否 | OpenRouter 文本动作 |
| [`OpenRouterResponseModel`](openrouter.md) | `openrouter_response` | `/responses` | 是 | OpenRouter Responses |
| [`PortkeyModel`](portkey.md) | `portkey` | `/chat/completions` | 是 | Portkey 网关 |
| [`PortkeyResponseAPIModel`](portkey_response.md) | `portkey_response` | `/responses` | 是 | Portkey Responses |
| [`RequestyModel`](requesty.md) | `requesty` | `/chat/completions` | 是 | Requesty 网关 |
| [`DeterministicModel`](test_models.md) | `deterministic` | 无 | 否 | 返回固定输出用于验证 |
| [`RouletteModel`](extra.md) | 使用完整类路径 | 元模型 | 否 | 随机选择已有适配器 |
| [`InterleavingModel`](extra.md) | 使用完整类路径 | 元模型 | 否 | 顺序轮换已有适配器 |

元模型组合不自动兼容所有注册能力。
