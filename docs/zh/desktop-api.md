[English](../desktop-api.md) · [简体中文](desktop-api.md)

# 桌面接口边界

桌面服务是当前所有者的本机应用接口，不是公开多租户 API。连接文件必须保持私有。

## 本机传输

启动器生成含 `url`、`token` 的连接文件。服务绑定数字地址 `127.0.0.1`，token 至少 32 字符。Electron 主进程读取文件；渲染层通过固定 preload 方法调用，不获得传输 token。

| 请求 | 返回 | 边界 |
| --- | --- | --- |
| `GET /health` | `ok`、`protocolVersion`、`cursor` | 需 Bearer 认证，不执行模型。 |
| `POST /invoke` | `{result: ...}` 或 `{error: ...}` | 需认证，拒绝带浏览器 Origin 的请求；JSON 对象正文最多 12 MB。 |
| `GET /events?after=<cursor>` | `cursor`、`events`，可有 `reset` | 带认证长轮询；重置后重新加载会话基线。 |

```http
POST /invoke HTTP/1.1
Host: 127.0.0.1:<port>
Authorization: Bearer <private-token>
Content-Type: application/json

{"method":"listAllSessions","args":{}}
```

示例 token 仅为占位符。不要通过公开反向代理暴露本机服务。未知方法明确失败；失败的有副作用请求不会自动重放。

## 应用方法

完整字段类型见 `desktop/src/contracts`，路由见 `src/vera/desktop/service.py` 和 `capabilities.py`。

| 领域 | 方法示例 | 副作用及条件 |
| --- | --- | --- |
| 会话 | `createSession`、`prompt`、`abort`、`getSessionBaseline` | 项目必须存在；运行中的会话拒绝修改配置和历史。 |
| 权限 | `setSessionSelections`、`respondPermission` | 允许一次或拒绝；审批绑定请求及活动会话。 |
| 模型 | `listProviders`、`listModels`、`addCustomProvider` | 可返回凭据是否存在，不返回已保存的密钥。 |
| MCP / Skills / 插件 | `probeMcpServer`、`getLoadedResources`、`pluginAction` | 测试连接会启动配置的传输并读取工具清单；安装与启用分开。 |
| 后台任务 | `saveScheduledTask`、`scheduledAction`、`runTaskboardTask` | 定时执行需显式无人值守策略；看板执行核对当前任务状态。 |
| 清理 | `previewSessionProjectDeletion`、`deleteSessionProject` | 预览令牌有时限且只用一次；清理会话记录，不删除项目源码。 |
| 媒体 | 见 `media_maintenance.py` 方法表 | 显式确认，核对权威会话、备份及内容指纹。 |

已认证的本机调用者具有桌面所有者权限。客户端按上述方法契约调用接口。

## LAN 与消息渠道

LAN 每次启动默认关闭。开启后使用独立 HTTP 监听和新配对 token，token 放在链接片段中。`GET /api/snapshot` 需 token；`POST /api/action` 还需单独允许远程控制，且仅接受 `prompt`、`abort`、`respondPermission`。请求检查 Host、Origin 和当前会话，远程消息不允许修改配置的斜杠命令。

LAN 使用明文 HTTP，仅在可信私有网络使用。持有配对链接即获得相应可见性，不要公开链接；关闭监听即撤销 token。消息渠道使用各平台身份、已配对用户白名单和会话路由，见[远程渠道](channels.md)。

可选任务看板另有回环能力链接和上游 HTTP 实现；桌面服务认证不能代替该服务的路由控制。
