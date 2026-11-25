[English](../../advanced/global_configuration.md) · [简体中文](global_configuration.md)

# 全局配置

!!! abstract "环境变量与私有 .env"

    启动会打印当前配置文件路径；进程环境优先于 dotenv。全局配置目录可由变量覆盖，品牌更名时已有目录和凭据按兼容策略读取，不应直接删除旧数据。

config setup 交互填写模型和凭据；set/unset 修改指定键；edit 使用 EDITOR 或默认 nano，主机需实际安装该编辑器。敏感值省略在命令行中，走提示输入，避免历史记录泄露。

## 变量职责

LiteLLM、OpenRouter 和 Portkey 适配器支持 `VERA_COST_TRACKING` 的 `default`、`ignore_errors`、`tokens` 三种值。`tokens` 只记录服务商报告的用量，不确定金额；兼容字段中的零费用不表示请求免费。

新配置默认写入 VERA 用户配置目录；仅有旧目录时复用，`VERA_GLOBAL_CONFIG_DIR` 显式指定时优先。供应商凭据变量沿用供应商名称，不因为产品品牌改名而更改。

| 变量 | 职责 |
| --- | --- |
| `VERA_MODEL_NAME` | 默认供应商/模型标识 |
| 供应商专用凭据变量 | 所选模型适配器认证 |
| `LITELLM_MODEL_REGISTRY_PATH` | 额外模型价格 registry JSON |
| `VERA_COST_TRACKING` | 费用元数据错误策略；忽略错误不是费用上限 |
| `VERA_GLOBAL_CALL_LIMIT` / `VERA_GLOBAL_COST_LIMIT` | 进程级调用/费用记账限制；零表示禁用 |
| `VERA_MODEL_RETRY_STOP_AFTER_ATTEMPT` | 模型请求重试次数 |
| `VERA_GLOBAL_CONFIG_DIR` | 全局私有配置目录 |
| `VERA_CONFIG_DIR` | 额外配置查找目录 |
| `VERA_CONFIG_PATH` | 默认终端 YAML 路径 |
| `VERA_INSPECTOR_STYLE_PATH` | Inspector 样式覆盖 |
| `VERA_BASH_PATH` | Windows Git Bash 可执行文件路径 |
| `VERA_SILENT_STARTUP` | 抑制启动横幅，适用于机器可读输出 |
| `VERA_DEFAULT_RUN` | 模块启动器的默认 Python 入口 |

价格 registry 用于额外模型费用元数据，忽略价格错误不是费用上限。YAML 保存模块行为与路径；channels、sandbox profiles、MCP 和 scheduler 使用各自的配置/状态库，不把所有配置当成同一 Schema。不要向前端发送完整环境或私有配置对象。

## 配置、命令与源码示例

```bash
vera-extra config setup
vera-extra config set VERA_MODEL_NAME openai/YOUR_MODEL
vera-extra config unset VERA_MODEL_NAME
vera-extra config edit
```
