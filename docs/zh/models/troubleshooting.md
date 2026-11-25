[English](../../models/troubleshooting.md) · [简体中文](troubleshooting.md)

# 模型排错

!!! abstract "先保留真实错误"

    检查适配器、provider/model、凭据变量和 API 地址，再考虑改代码。未指明来源的 401 不能归因给另一服务，问题报告不能含密钥值。

## 认证、费用与参数

认证异常需核对有效凭据、账号模型权限及地址；LiteLLM 模型漏前缀可能选择其他供应商并报看似无关的凭据错误。用 setup 或私有配置编辑更新，注意进程环境覆盖文件，后台服务需重启才继承新环境。

费用异常通常来自未知模型/缺 usage，按[本地模型](local_models.md)注册价格；Portkey 的网关名可用 litellm_model_name_override 映射。忽略错误可能低报成本，不会免费。

温度、reasoning、token 限额和工具 Schema 支持因模型而异，移除不支持的 model_kwargs，按实际 Provider 校验。文本适配器不能声明 MCP/plan 等命名工具。

## 网络、预算与格式

核对 provider 状态、超时和重试策略；格式错误保留返回内容和已计费用，连续错误触发停止。预算和取消在边界生效，已发出的请求可能继续。报告时提供 run ID、候选版本、脱敏配置和实际错误，不发送全部环境变量或凭据。

## 配置、命令与源码示例

```bash
vera-extra config setup
vera-extra config edit
```
